from datetime import datetime, date, timedelta
import json

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DIFY_AGENT_KEY, DIFY_BASE_URL, WORK_START
from ..database import get_db
from ..models import Attendance, Employee
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/attendance", tags=["考勤"])


class CheckinIn(BaseModel):
    type: str = "clock_in"   # clock_in / clock_out


class AskIn(BaseModel):
    question: str = ""       # 用户自然语言提问，如「这个月我考勤多少天」


class QueryIn(BaseModel):
    """查询接口入参。"""
    emp_id: int
    period: str = "month"            # month / week / last_week / last_month / specific
    intent: str = "days"             # days / late / avg_time / specific_day / all
    target_date: str | None = None   # intent=specific_day 时使用，YYYY-MM-DD
    start_date: str | None = None    # 自定义区间开始
    end_date: str | None = None      # 自定义区间结束


def _period_start(period: str) -> date:
    today = date.today()
    if period == "week":
        return today - timedelta(days=today.weekday())
    return today.replace(day=1)


def _range_of(period: str) -> tuple[date, date]:
    """周期 → (start, end)。供 /command 一句话打卡入口复用。"""
    today = date.today()
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "last_week":
        s = today - timedelta(days=today.weekday() + 7)
        return s, s + timedelta(days=6)
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    return today.replace(day=1), today          # month（默认）


def _workdays_between(start: date, end: date) -> int:
    """区间内周一~周五且已过去的工作日数（用于算缺勤）。"""
    today, n, d = date.today(), 0, start
    while d <= end:
        if d.weekday() < 5 and d <= today:
            n += 1
        d += timedelta(days=1)
    return n


def _stats_for(db: Session, employee_pk: int, start: date, end: date,
               period_label: str) -> dict:
    """单员工在 [start, end] 区间内的考勤统计（全部由后端计算）。"""
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == employee_pk,
        Attendance.work_date >= start,
        Attendance.work_date <= end,
    ).order_by(Attendance.checkin_time)).all()

    ins = [r for r in rows if r.type == "clock_in"]
    days = len({r.work_date for r in ins})
    late_count = sum(1 for r in ins if r.is_late)
    times = sorted(r.checkin_time.strftime("%H:%M") for r in ins)

    avg_clock_in = ""
    if times:
        total = sum(int(t[:2]) * 60 + int(t[3:]) for t in times)
        avg_clock_in = f"{total // len(times) // 60:02d}:{total // len(times) % 60:02d}"

    workdays = _workdays_between(start, end)
    return {
        "period": period_label,
        "range_start": str(start), "range_end": str(end),
        "workdays": workdays, "days": days,
        "absent_days": max(workdays - days, 0),
        "late_count": late_count,
        "late_rate": f"{late_count / days * 100:.0f}%" if days else "0%",
        "avg_clock_in": avg_clock_in,
        "earliest": times[0] if times else "",
        "latest": times[-1] if times else "",
        "record_count": len(rows),
    }


def _local_parse_action(text: str) -> str:
    """本地规则识别指令类型（确定性兜底，不依赖外部 AI）。"""
    t = text or ""
    if any(k in t for k in ("下班", "签退", "收工")):
        return "clock_out"
    return "clock_in"


def _local_summary(data: dict) -> str:
    """把后端算好的周/月统计拼成自然语言（不依赖 LLM）。"""
    c, w, m = data["checkin"], data["week"], data["month"]
    parts = [c["message"]]
    parts.append(
        f"本周（{w['range_start']} 起）已出勤 {w['days']} 天、迟到 {w['late_count']} 次"
        + (f"，平均到岗 {w['avg_clock_in']}" if w["avg_clock_in"] else "")
    )
    parts.append(
        f"本月（{m['range_start']} 起）已出勤 {m['days']} 天、迟到 {m['late_count']} 次"
        + (f"，平均到岗 {m['avg_clock_in']}" if m["avg_clock_in"] else "")
    )
    if m["late_count"] == 0 and m["days"] > 0:
        parts.append("本月全勤未迟到，继续保持")
    elif m["late_count"] >= 3:
        parts.append("本月迟到偏多，建议提前安排通勤")
    return "；".join(parts) + "。"


@router.post("/checkin")
def checkin(body: CheckinIn, user: Employee = Depends(get_current_user),
            db: Session = Depends(get_db)):
    if body.type not in ("clock_in", "clock_out"):
        raise HTTPException(422, "type 必须为 clock_in 或 clock_out")
    now = datetime.now()
    today = now.date()
    dup = db.scalar(select(Attendance).where(
        Attendance.employee_id == user.employee_id,
        Attendance.work_date == today,
        Attendance.type == body.type,
    ))
    if dup:
        return {
            "time": dup.checkin_time.isoformat(), "type": dup.type,
            "is_late": dup.is_late, "message": "今天已打过该卡，未重复记录",
        }
    hh, mm = map(int, WORK_START.split(":"))
    is_late = body.type == "clock_in" and (
        now.hour * 60 + now.minute > hh * 60 + mm
    )
    rec = Attendance(employee_id=user.employee_id, checkin_time=now, type=body.type,
                     is_late=is_late, work_date=today)
    db.add(rec)
    db.commit()
    msg = "打卡成功" + ("，注意：已超过上班时间 09:00，记为迟到" if is_late else "")
    return {"time": now.isoformat(), "type": body.type, "is_late": is_late, "message": msg}


@router.get("/my")
def my_attendance(period: str = Query(..., pattern="^(week|month)$"),
                   user: Employee = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    start = _period_start(period)
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == user.employee_id,
        Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time)).all()
    return {"records": [r.to_dict() for r in rows]}


@router.post("/ask")
async def attendance_ask(body: AskIn,
                         user: Employee = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """悬浮气泡入口：统一智能体（Dify Agent），集合所有工作流。"""
    q = (body.question or "").strip() or "这个月我的考勤情况"

    # 有 Key → 调 Dify 统一智能体（Agent 只支持 streaming 模式）
    if DIFY_AGENT_KEY:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    f"{DIFY_BASE_URL.rstrip('/')}/chat-messages",
                    headers={
                        "Authorization": f"Bearer {DIFY_AGENT_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": q,
                        "response_mode": "streaming",
                        "user": str(user.employee_id),
                        "inputs": {"emp_id": str(user.employee_id), "emp_name": user.name},
                    },
                ) as resp:
                    resp.raise_for_status()
                    parts = []
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                content = (chunk.get("answer") or "")
                                if not content:
                                    continue
                                # Dify Agent 流式响应里 answer 可能既发增量又发全量
                                # （全量 chunk 会把前面内容整段重发），需去重避免重复。
                                prev = "".join(parts)
                                if prev and content.startswith(prev):
                                    parts = [content]          # 全量覆盖
                                elif prev:
                                    ov = 0
                                    for i in range(1, min(len(prev), len(content)) + 1):
                                        if prev.endswith(content[:i]):
                                            ov = i
                                    parts.append(content[ov:])  # 增量/重叠：截掉重复前缀
                                else:
                                    parts.append(content)
                            except (json.JSONDecodeError, KeyError):
                                continue
            answer = "".join(parts) or "智能体未返回内容"
            return {"answer": answer, "ai": True}
        except Exception as e:
            # Dify 不可用时降级到本地兜底
            return {"answer": _local_fallback(q, user, db), "ai": False}

    # 无 Key → 纯本地
    return {"answer": _local_fallback(q, user, db), "ai": False}


def _local_fallback(q: str, user: Employee, db: Session) -> str:
    """Dify 不可用时的本地兜底回答（仅考勤统计）。"""
    period = "week" if any(w in q for w in ("本周", "这周", "这星期", "周考勤")) else "month"
    start = _period_start(period)
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == user.employee_id,
        Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time)).all()

    clock_ins = [r for r in rows if r.type == "clock_in"]
    days = len({r.work_date for r in clock_ins})
    late_count = sum(1 for r in clock_ins if r.is_late)
    times = sorted(r.checkin_time.strftime("%H:%M") for r in clock_ins) if clock_ins else []

    avg_clock_in = ""
    if clock_ins:
        total_min = sum(r.checkin_time.hour * 60 + r.checkin_time.minute for r in clock_ins)
        avg_clock_in = f"{total_min // len(clock_ins) // 60:02d}:{total_min // len(clock_ins) % 60:02d}"

    period_cn = "本周" if period == "week" else "本月"
    parts = [
        f"{user.name}{period_cn}已出勤 {days} 天",
        f"迟到 {late_count} 次",
        f"平均上班打卡时间 {avg_clock_in}" if avg_clock_in else "",
    ]
    if late_count == 0:
        parts.append("出勤表现很好，请继续保持！")
    elif late_count >= 3:
        parts.append("迟到次数偏多，建议优化通勤安排哦。")
    else:
        parts.append("偶有迟到，注意按时到岗。")
    return "，".join(p for p in parts if p) + "。"


class CommandIn(BaseModel):
    """员工端指令入口入参。"""
    command: str = ""      # 例：「上班打卡」「打卡」「下班打卡」


@router.post("/command")
async def attendance_command(body: CommandIn,
                             user: Employee = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """员工端一句话指令入口：打卡 / 查考勤（本地规则执行，不依赖外部 AI）。"""
    cmd = (body.command or "").strip() or "打卡"
    action = _local_parse_action(cmd)
    data = _do_checkin(str(user.employee_id), action, cmd, db)
    return {"answer": _local_summary(data), "ai": False, "command": cmd, "data": data}


def _resolve_period_range(period: str, target_date: str | None,
                          start_date: str | None, end_date: str | None) -> tuple[date, date]:
    """把周期解析成 (start, end) 日期区间。"""
    today = date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period == "last_month":
        first_this = today.replace(day=1)
        end_last = first_this - timedelta(days=1)
        start_last = end_last.replace(day=1)
        return start_last, end_last
    if period == "specific" and target_date:
        d = date.fromisoformat(target_date)
        return d, d
    if period == "custom" and start_date and end_date:
        return date.fromisoformat(start_date), date.fromisoformat(end_date)
    # 默认本月
    return today.replace(day=1), today


@router.post("/query")
def attendance_query(body: QueryIn, db: Session = Depends(get_db)):
    """数据库查询接口：接收结构化参数，返回原始考勤记录 JSON。"""
    emp = db.scalar(select(Employee).where(Employee.employee_id == body.emp_id))
    if not emp:
        raise HTTPException(404, f"员工工号 {body.emp_id} 不存在")

    try:
        start, end = _resolve_period_range(body.period, body.target_date,
                                           body.start_date, body.end_date)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"日期解析失败：{e}")

    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == emp.employee_id,
        Attendance.work_date >= start,
        Attendance.work_date <= end,
    ).order_by(Attendance.checkin_time)).all()

    records = []
    for r in rows:
        records.append({
            "work_date": str(r.work_date),
            "type": r.type,
            "checkin_time": r.checkin_time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_late": bool(r.is_late),
            "work_start": WORK_START,
        })

    clock_ins = [r for r in records if r["type"] == "clock_in"]
    days = len({r["work_date"] for r in clock_ins})
    late_count = sum(1 for r in clock_ins if r["is_late"])
    times = sorted(r["checkin_time"][11:16] for r in clock_ins) if clock_ins else []
    avg_clock_in = ""
    if clock_ins:
        total_min = sum(int(t[:2]) * 60 + int(t[3:5]) for t in times)
        avg_clock_in = f"{total_min // len(clock_ins) // 60:02d}:{total_min // len(clock_ins) % 60:02d}"

    return {
        "employee": {
            "emp_id": emp.employee_id,
            "name": emp.name,
            "department": emp.department,
            "position": emp.position,
        },
        "query": {
            "period": body.period,
            "intent": body.intent,
            "target_date": body.target_date,
            "range_start": str(start),
            "range_end": str(end),
        },
        "stats": {
            "days": days,
            "late_count": late_count,
            "avg_clock_in": avg_clock_in,
            "earliest": times[0] if times else "",
            "latest": times[-1] if times else "",
            "record_count": len(records),
        },
        "records": records,
    }


@router.get("/report")
async def attendance_report(period: str = Query("week", pattern="^(week|month)$"),
                            dept: str = Query(None),
                            manager: Employee = Depends(require_manager),
                            db: Session = Depends(get_db)):
    # 管理端数据隔离：只能看自己 permissions 覆盖岗位的员工
    perms = set(manager.permission_list)
    emps = db.scalars(select(Employee)).all()
    visible = [e for e in emps if (not perms or perms == set()) or
               e.position in perms or e.id == manager.id]
    # 总经办（权限含部门名）看全部
    if any(p.endswith(("部", "队", "办")) for p in perms) or len(perms) >= 5:
        visible = emps
    if dept:
        visible = [e for e in visible if e.department == dept]
    ids = [e.employee_id for e in visible]
    name_map = {e.employee_id: e.name for e in visible}

    start = _period_start(period)
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id.in_(ids), Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time.desc())).all()

    late_records = [r for r in rows if r.is_late]
    late_count = {}
    for r in late_records:
        late_count[r.employee_id] = late_count.get(r.employee_id, 0) + 1
    late_top = sorted(late_count.items(), key=lambda x: -x[1])[:5]
    late_top_str = "、".join(f"{name_map.get(i, i)}{c}次" for i, c in late_top)

    stats = {
        "record_count": len(rows),
        "late_count": len(late_records),
        "late_top": [{"name": name_map.get(i, str(i)), "count": c} for i, c in late_top],
        "late_top_str": late_top_str,
    }
    return {
        "period": period,
        "range_start": str(start),
        "rows": [{**r.to_dict(), "employee_name": name_map.get(r.employee_id, "")} for r in rows],
        "stats": stats,
    }


# ============================================================
# 员工端一句话打卡的内部实现（无外部 AI 依赖）
# 时间、迟到判定、统计聚合一律由后端完成。
# ============================================================
def _do_checkin(emp_id_str: str, action: str, command: str, db: Session) -> dict:
    """员工打卡（本地执行）：记录打卡、判迟到、返回本次结果 + 周/月统计。

    供 /command 一句话指令入口使用。
    """
    if not str(emp_id_str).strip().isdigit():
        raise HTTPException(400, "emp_id 必须是数字工号")
    emp = db.scalar(select(Employee).where(Employee.employee_id == int(emp_id_str)))
    if not emp:
        raise HTTPException(404, f"员工工号 {emp_id_str} 不存在")
    action = action if action in ("clock_in", "clock_out") else "clock_in"

    now = datetime.now()
    today = now.date()
    hh, mm = map(int, WORK_START.split(":"))

    dup = db.scalar(select(Attendance).where(
        Attendance.employee_id == emp.employee_id,
        Attendance.work_date == today,
        Attendance.type == action,
    ))
    label = "下班" if action == "clock_out" else "上班"
    if dup:
        checkin_result = {
            "success": False, "duplicated": True,
            "time": dup.checkin_time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action, "is_late": bool(dup.is_late),
            "late_minutes": 0, "work_start": WORK_START,
            "message": (f"你今天已打过{label}卡"
                        f"（{dup.checkin_time:%H:%M}），本次未重复记录"),
        }
    else:
        late_minutes = 0
        if action == "clock_in":
            late_minutes = max(now.hour * 60 + now.minute - (hh * 60 + mm), 0)
        is_late = action == "clock_in" and late_minutes > 0
        db.add(Attendance(employee_id=emp.employee_id, checkin_time=now, type=action,
                          is_late=is_late, work_date=today))
        db.commit()
        tail = (f"，已超过上班时间 {WORK_START}，迟到 {late_minutes} 分钟"
                if is_late else "，未迟到")
        checkin_result = {
            "success": True, "duplicated": False,
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action, "is_late": is_late,
            "late_minutes": late_minutes, "work_start": WORK_START,
            "message": f"{label}打卡成功（{now:%H:%M}）{tail}",
        }

    w_s, w_e = _range_of("week")
    m_s, m_e = _range_of("month")
    return {
        "employee": {"emp_id": emp.employee_id, "name": emp.name,
                     "department": emp.department, "position": emp.position},
        "command": command, "action": action,
        "checkin": checkin_result,
        "week": _stats_for(db, emp.employee_id, w_s, w_e, "week"),
        "month": _stats_for(db, emp.employee_id, m_s, m_e, "month"),
    }
