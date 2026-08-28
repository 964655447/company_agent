from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import WORK_START
from ..database import get_db
from ..dify_client import wf5_analysis, wf6_attendance_qa, wf7_checkin, wf8_team_report
from ..models import Attendance, Employee
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/attendance", tags=["考勤"])


class CheckinIn(BaseModel):
    type: str = "clock_in"   # clock_in / clock_out


class AskIn(BaseModel):
    question: str = ""       # 用户自然语言提问，如「这个月我考勤多少天」


class QueryIn(BaseModel):
    """供 Dify HTTP 节点调用的查询接口入参。"""
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
    """周期 → (start, end)。供 Dify WF-7 / WF-8 复用。"""
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
    """单员工在 [start, end] 区间内的考勤统计（全部由后端计算，不经过 LLM）。"""
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


def _behavior(days: int, late_count: int, workdays: int) -> str:
    """规则化行为标签（确定性规则放后端，AI 只做解读与建议）。"""
    if days == 0:
        return "无考勤记录"
    if late_count == 0 and workdays and days >= workdays:
        return "全勤稳定"
    if late_count == 0:
        return "出勤良好"
    if late_count <= 1:
        return "基本正常"
    if late_count <= 3:
        return "偶有迟到"
    return "迟到偏多"


def _action_label(action: str) -> str:
    return "上班" if action == "clock_in" else "下班"


@router.post("/checkin")
def checkin(body: CheckinIn, user: Employee = Depends(get_current_user),
            db: Session = Depends(get_db)):
    if body.type not in ("clock_in", "clock_out"):
        raise HTTPException(422, "type 必须为 clock_in 或 clock_out")
    now = datetime.now()
    today = now.date()
    dup = db.scalar(select(Attendance).where(
        Attendance.employee_id == user.id,
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
    rec = Attendance(employee_id=user.id, checkin_time=now, type=body.type,
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
        Attendance.employee_id == user.id,
        Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time)).all()
    return {"records": [r.to_dict() for r in rows]}


@router.post("/ask")
async def attendance_ask(body: AskIn,
                         user: Employee = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """考勤智能问答（悬浮气泡入口）：后端从 MySQL 统计数字 → Dify WF-6 生成回答。"""
    q = (body.question or "").strip() or "这个月我的考勤情况"
    # 简单周期识别：问「周」就查本周，否则默认本月
    period = "week" if any(w in q for w in ("本周", "这周", "这星期", "周考勤")) else "month"
    start = _period_start(period)
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == user.id,
        Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time)).all()

    clock_ins = [r for r in rows if r.type == "clock_in"]
    days = len({r.work_date for r in clock_ins})
    late_count = sum(1 for r in clock_ins if r.is_late)
    times = sorted(r.checkin_time.strftime("%H:%M") for r in clock_ins) if clock_ins else []

    # 平均上班打卡时间
    avg_clock_in = ""
    if clock_ins:
        total_min = sum(r.checkin_time.hour * 60 + r.checkin_time.minute for r in clock_ins)
        avg_clock_in = f"{total_min // len(clock_ins) // 60:02d}:{total_min // len(clock_ins) % 60:02d}"

    stats = {
        "period": period,
        "period_label": f"{date.today():%Y年%m月}" if period == "month"
        else f"{date.today():%Y年%m月%d日} 起的本周",
        "employee_name": user.name,
        "days": days,
        "record_count": len(rows),
        "late_count": late_count,
        "avg_clock_in": avg_clock_in,
        "earliest": times[0] if times else "",
        "latest": times[-1] if times else "",
        "work_start": WORK_START,
    }
    result = await wf6_attendance_qa(
        q,
        {"name": user.name, "position": user.position, "department": user.department},
        stats,
        str(user.emp_id),
    )
    return {"answer": result["answer"], "ai": result["ai"], "stats": stats}


class CommandIn(BaseModel):
    """员工端指令入口入参。"""
    command: str = ""      # 例：「上班打卡」「打卡」「下班打卡」


def _local_parse_action(text: str) -> str:
    """本地规则识别指令类型（Dify 可用与否都必须有确定性兜底）。"""
    t = text or ""
    if any(k in t for k in ("下班", "签退", "收工")):
        return "clock_out"
    return "clock_in"


def _local_summary(data: dict) -> str:
    """降级话术：把后端算好的周/月统计拼成自然语言（不经过 LLM）。"""
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


@router.post("/command")
async def attendance_command(body: CommandIn,
                             user: Employee = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """员工端一句话指令入口：打卡 / 查考勤。

    正常链路：Dify WF-7 理解指令 → 回调本服务 /wf-checkin 完成打卡、
    迟到判定与周/月统计 → LLM 生成播报话术。
    降级链路：Dify 未接入或调用失败时，后端本地执行完全相同的打卡与统计，
    仅话术退化为模板拼接，功能不受影响。
    """
    cmd = (body.command or "").strip() or "打卡"
    result = await wf7_checkin(cmd, str(user.emp_id), str(user.emp_id))
    if result.get("ai"):
        return {"answer": result["answer"], "ai": True, "command": cmd, "data": None}

    data = wf_checkin(
        WfCheckinIn(emp_id=str(user.emp_id), action=_local_parse_action(cmd), command=cmd), db
    )
    return {"answer": _local_summary(data), "ai": False, "command": cmd, "data": data}


def _resolve_period_range(period: str, target_date: str | None,
                          start_date: str | None, end_date: str | None) -> tuple[date, date]:
    """把 LLM 识别出的 period 解析成 (start, end) 日期区间。"""
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
    """供 Dify HTTP 节点调用的数据库查询接口（无认证，仅内网/Dify 用）。

    接收 LLM 识别出的结构化参数，返回原始考勤记录 JSON。
    Dify LLM 节点基于此 JSON 生成自然语言回答。
    """
    emp = db.scalar(select(Employee).where(Employee.emp_id == body.emp_id))
    if not emp:
        raise HTTPException(404, f"员工工号 {body.emp_id} 不存在")

    try:
        start, end = _resolve_period_range(body.period, body.target_date,
                                           body.start_date, body.end_date)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"日期解析失败：{e}")

    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == emp.id,
        Attendance.work_date >= start,
        Attendance.work_date <= end,
    ).order_by(Attendance.checkin_time)).all()

    records = []
    for r in rows:
        records.append({
            "work_date": str(r.work_date),
            "type": r.type,                       # clock_in / clock_out
            "checkin_time": r.checkin_time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_late": bool(r.is_late),
            "work_start": WORK_START,
        })

    # 顺带算几个常用统计，供 LLM 直接引用（不强制使用）
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
            "emp_id": emp.emp_id,
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
    ids = [e.id for e in visible]
    name_map = {e.id: e.name for e in visible}

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
    # 优先走 WF-8（逐员工生成周/月度数据 + AI 员工行为分析）；
    # 未接入或调用失败时回退到 WF-5 的模板分析，页面照常可用。
    analysis = await wf8_team_report(period, dept, manager.emp_id, str(manager.emp_id))
    if not analysis:
        analysis = await wf5_analysis("attendance", f"{date.today():%Y-%m}", stats,
                                      str(manager.emp_id))
    return {
        "period": period,
        "range_start": str(start),
        "rows": [{**r.to_dict(), "employee_name": name_map.get(r.employee_id, "")} for r in rows],
        "stats": stats,
        "analysis": analysis,
    }


# ============================================================
# 供 Dify WF-7 / WF-8 调用的内部接口（无认证，仅内网 Dify 可达）
# 设计原则：时间、迟到判定、统计聚合一律由后端完成，Dify 只做
#           自然语言理解与生成，不参与任何数值计算或写库决策。
# ============================================================
class WfCheckinIn(BaseModel):
    """WF-7 入参：员工打卡指令。

    字段统一用 str 接收——Dify 变量未填写时会传空字符串，
    用 int 接收会直接 422，容错性太差。
    """
    emp_id: str = ""
    action: str = "clock_in"     # clock_in / clock_out
    command: str = ""            # 员工原始指令原文，仅用于回显


@router.post("/wf-checkin")
def wf_checkin(body: WfCheckinIn, db: Session = Depends(get_db)):
    """WF-7：记录打卡上传时间 → 判断是否迟到 → 返回周/月度统计。

    与 /checkin 的区别：本接口不校验 JWT（Dify 侧调用），
    并在一次响应里同时给出「本次打卡结果 + 本周统计 + 本月统计」。
    """
    if not str(body.emp_id).strip().isdigit():
        raise HTTPException(400, "emp_id 必须是数字工号")
    emp = db.scalar(select(Employee).where(Employee.emp_id == int(body.emp_id)))
    if not emp:
        raise HTTPException(404, f"员工工号 {body.emp_id} 不存在")
    action = body.action if body.action in ("clock_in", "clock_out") else "clock_in"

    now = datetime.now()
    today = now.date()
    hh, mm = map(int, WORK_START.split(":"))

    dup = db.scalar(select(Attendance).where(
        Attendance.employee_id == emp.id,
        Attendance.work_date == today,
        Attendance.type == action,
    ))
    if dup:
        checkin_result = {
            "success": False, "duplicated": True,
            "time": dup.checkin_time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action, "is_late": bool(dup.is_late),
            "late_minutes": 0, "work_start": WORK_START,
            "message": (f"你今天已打过{_action_label(action)}卡"
                        f"（{dup.checkin_time:%H:%M}），本次未重复记录"),
        }
    else:
        late_minutes = 0
        if action == "clock_in":
            late_minutes = max(now.hour * 60 + now.minute - (hh * 60 + mm), 0)
        is_late = action == "clock_in" and late_minutes > 0
        db.add(Attendance(employee_id=emp.id, checkin_time=now, type=action,
                          is_late=is_late, work_date=today))
        db.commit()
        tail = (f"，已超过上班时间 {WORK_START}，迟到 {late_minutes} 分钟"
                if is_late else "，未迟到")
        checkin_result = {
            "success": True, "duplicated": False,
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "type": action, "is_late": is_late,
            "late_minutes": late_minutes, "work_start": WORK_START,
            "message": f"{_action_label(action)}打卡成功（{now:%H:%M}）{tail}",
        }

    w_s, w_e = _range_of("week")
    m_s, m_e = _range_of("month")
    return {
        "employee": {"emp_id": emp.emp_id, "name": emp.name,
                     "department": emp.department, "position": emp.position},
        "command": body.command, "action": action,
        "checkin": checkin_result,
        "week": _stats_for(db, emp.id, w_s, w_e, "week"),
        "month": _stats_for(db, emp.id, m_s, m_e, "month"),
    }


class WfTeamReportIn(BaseModel):
    """WF-8 入参：管理端考勤分析（同样对 Dify 空串做容错）。"""
    period: str = "week"          # week / month / last_week / last_month
    dept: str | None = None       # 部门过滤，留空=全部
    manager_id: str | None = None # 调用者工号，用于数据权限隔离
    top_n: int = 50               # 最多返回多少名员工明细


@router.post("/wf-team-report")
def wf_team_report(body: WfTeamReportIn, db: Session = Depends(get_db)):
    """WF-8：按员工聚合周/月度考勤数据 + 行为标签，供 AI 分析员工行为。

    数据权限与 /report 保持一致（管理者只能看自己权限覆盖的员工）。
    """
    period = (body.period or "week").strip() or "week"
    if period not in ("week", "month", "last_week", "last_month"):
        period = "week"
    dept = (body.dept or "").strip() or None
    mid = int(body.manager_id) if str(body.manager_id or "").strip().isdigit() else None

    emps = list(db.scalars(select(Employee)).all())

    if mid:                                   # 管理者视角：按权限过滤
        mgr = db.scalar(select(Employee).where(Employee.emp_id == mid))
        if mgr and mgr.role == "manager":
            perms = set(mgr.permission_list)
            if perms and not (any(p.endswith(("部", "队", "办")) for p in perms)
                              or len(perms) >= 5):
                emps = [e for e in emps if e.position in perms or e.id == mgr.id]
    if dept:
        emps = [e for e in emps if e.department == dept]

    start, end = _range_of(period)
    rows = []
    for e in emps:
        st = _stats_for(db, e.id, start, end, period)
        rows.append({
            "emp_id": e.emp_id, "name": e.name,
            "department": e.department, "position": e.position,
            "days": st["days"], "workdays": st["workdays"],
            "absent_days": st["absent_days"],
            "late_count": st["late_count"], "late_rate": st["late_rate"],
            "avg_clock_in": st["avg_clock_in"],
            "earliest": st["earliest"], "latest": st["latest"],
            "behavior": _behavior(st["days"], st["late_count"], st["workdays"]),
        })
    rows.sort(key=lambda x: (-x["late_count"], x["days"]))   # 迟到多的排前面

    headcount = len(rows)
    total_days = sum(x["days"] for x in rows)
    total_late = sum(x["late_count"] for x in rows)
    total_workdays = sum(x["workdays"] for x in rows)
    punctual = sorted(rows, key=lambda x: (-x["days"], x["late_count"]))

    summary = {
        "headcount": headcount,
        "total_days": total_days,
        "total_late": total_late,
        "avg_days": round(total_days / headcount, 1) if headcount else 0,
        "attendance_rate": f"{total_days / total_workdays * 100:.1f}%" if total_workdays else "0%",
        "late_rate": f"{total_late / total_days * 100:.1f}%" if total_days else "0%",
        "late_top": [{"name": x["name"], "late_count": x["late_count"]}
                     for x in rows[:5] if x["late_count"] > 0],
        "punctual_top": [{"name": x["name"], "days": x["days"]}
                         for x in punctual if x["days"] > 0][:5],
    }
    return {
        "period": period,
        "dept": dept or "全部部门",
        "range_start": str(start), "range_end": str(end),
        "work_start": WORK_START,
        "summary": summary,
        "employee_count": len(rows[:body.top_n]),
        "employees": rows[:body.top_n],
    }
