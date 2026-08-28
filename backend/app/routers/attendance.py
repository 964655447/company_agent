from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import WORK_START
from ..database import get_db
from ..dify_client import wf5_analysis, wf6_attendance_qa
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
    analysis = await wf5_analysis("attendance", f"{date.today():%Y-%m}", stats, str(manager.emp_id))
    return {
        "rows": [{**r.to_dict(), "employee_name": name_map.get(r.employee_id, "")} for r in rows],
        "stats": stats,
        "analysis": analysis,
    }
