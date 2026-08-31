from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..local_rules import wf4_fallback
from ..models import AssessmentLog, AssessmentStat, Employee
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/assessment", tags=["进阶考核"])


def _assess_period_range(period: str, target_month: str | None):
    """考核周期 → (start, end)，基于 test_time / created_at 过滤。"""
    today = date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "month":
        return today.replace(day=1), today
    if period == "last_month":
        first_this = today.replace(day=1)
        end_last = first_this - timedelta(days=1)
        return end_last.replace(day=1), end_last
    if period == "all":
        return None, None
    if period == "specific" and target_month and len(target_month) == 7:
        y, m = target_month.split("-")
        first = date(int(y), int(m), 1)
        last = (first.replace(month=int(m) + 1) - timedelta(days=1)) if int(m) < 12 else \
              first.replace(year=first.year + 1, month=1) - timedelta(days=1)
        return first, last
    return today.replace(day=1), today

router = APIRouter(prefix="/api/assessment", tags=["进阶考核"])


class QueryIn(BaseModel):
    position: str


@router.post("/query")
async def query_position(body: QueryIn,
                         user: Employee = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    position = body.position.strip()
    if not position:
        return {"intro": "请输入想了解的岗位名称"}
    result = wf4_fallback(position)
    # 结合实际数据：当前在岗人数 + 本人对该岗位的历史成绩
    holders = db.scalars(select(Employee).where(Employee.position == position)).all()
    result["holders_count"] = len(holders)
    my_stats = db.scalars(select(AssessmentStat).where(
        AssessmentStat.employee_id == user.employee_id,
        AssessmentStat.target_position == position,
    )).all()
    valid = [s.score for s in my_stats if s.score is not None]
    result["my_score"] = round(max(valid), 1) if valid else None
    db.add(AssessmentLog(employee_id=user.employee_id, position_queried=position))
    db.commit()
    return result


@router.get("/stats")
def stats(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    manager: Employee = Depends(require_manager),
    db: Session = Depends(get_db),
):
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentLog.position_queried, Employee.name, func.count(AssessmentLog.id)) \
        .join(Employee, AssessmentLog.employee_id == Employee.employee_id)
    if start:
        q = q.where(AssessmentLog.created_at >= datetime.combine(start, datetime.time.min))
    if end:
        q = q.where(AssessmentLog.created_at <= datetime.combine(end, datetime.time.max))
    rows = db.execute(
        q.group_by(AssessmentLog.position_queried, Employee.name)
         .order_by(func.count(AssessmentLog.id).desc())
    ).all()
    return {
        "rows": [{"name": r[1], "position_queried": r[0], "count": r[2]} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }


@router.get("/scores")
def my_scores(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人考核成绩（原岗位 / 意向岗位 / 成绩 / 测试时间）。"""
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentStat, Employee.name) \
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id) \
        .where(AssessmentStat.employee_id == user.employee_id)
    if start:
        q = q.where(AssessmentStat.test_time >= datetime.combine(start, datetime.time.min))
    if end:
        q = q.where(AssessmentStat.test_time <= datetime.combine(end, datetime.time.max))
    rows = db.execute(q.order_by(AssessmentStat.test_time.desc())).all()
    return {
        "scores": [{"name": r[1], **r[0].to_dict()} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }


@router.get("/scores/all")
def all_scores(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    manager: Employee = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """管理员：全员考核成绩汇总（按工号、测试时间倒序）。"""
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentStat, Employee.name) \
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id)
    if start:
        q = q.where(AssessmentStat.test_time >= datetime.combine(start, datetime.time.min))
    if end:
        q = q.where(AssessmentStat.test_time <= datetime.combine(end, datetime.time.max))
    rows = db.execute(q.order_by(AssessmentStat.employee_id, AssessmentStat.test_time.desc())).all()
    return {
        "scores": [{"name": r[1], **r[0].to_dict()} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }
