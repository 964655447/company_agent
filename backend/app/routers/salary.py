from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import BASE_SALARY_MAP, BASE_SALARY_DEFAULT, SUBSIDY_DEFAULT
from ..database import get_db
from ..local_rules import wf3_fallback
from ..models import Employee, Salary
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/salary", tags=["工资"])


def _salary_period_range(period: str, target_month: str | None):
    """工资周期 → (start, end)，基于 created_at 过滤。"""
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

# 绩效奖金上限（元）
PERF_BONUS_CAP = 10000.0


def _score_to_factor(score: float) -> float:
    """AI 绩效分数(0-100) → 绩效系数(DECIMAL 3,2)。
    映射：90+→1.20, 80+→1.00, 70+→0.80, 60+→0.60, <60→0.40。
    系数 1.0 对应奖金上限 PERF_BONUS_CAP。
    """
    if score >= 90:
        return 1.20
    if score >= 80:
        return 1.00
    if score >= 70:
        return 0.80
    if score >= 60:
        return 0.60
    return 0.40


class PerformanceIn(BaseModel):
    achievements: str


@router.post("/submit-performance")
async def submit_performance(body: PerformanceIn,
                             user: Employee = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    if not body.achievements.strip():
        return {"error": "achievements 不能为空"}
    # 绩效本地规则打分（AI 能力已整合至右下角「智能助手」，统一智能体接入中）
    result = wf3_fallback(body.achievements)
    score = float(result.get("performance_score", 60))
    base_salary = float(BASE_SALARY_MAP.get(user.position, BASE_SALARY_DEFAULT))
    factor = _score_to_factor(score)
    perf_bonus = round(min(base_salary * factor, PERF_BONUS_CAP), 2)
    allowance = SUBSIDY_DEFAULT
    gross = round(base_salary + perf_bonus + allowance, 2)

    rec = db.scalar(select(Salary).where(Salary.employee_id == str(user.employee_id)))
    if rec:  # 重复提交 → 覆盖本人工资核算
        rec.no, rec.name, rec.position = user.no, user.name, user.position
        rec.base_salary = base_salary
        rec.performance_rating = factor
        rec.performance_bonus, rec.allowance, rec.gross_salary = perf_bonus, allowance, gross
    else:
        rec = Salary(
            employee_id=str(user.employee_id), no=user.no, name=user.name, position=user.position,
            base_salary=base_salary, performance_rating=factor,
            performance_bonus=perf_bonus, allowance=allowance, gross_salary=gross,
        )
        db.add(rec)
    db.commit()
    return {
        **rec.to_dict(),
        "performance_score": score,
        "performance_factor": factor,
        "reasoning": result.get("reasoning", ""),
    }


@router.get("/my")
def my_salary(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 工资表为静态快照（每人一条），无 created_at 时间戳，
    # period 参数保留兼容前端统一筛选 UI，但不做时间过滤。
    rows = db.scalars(
        select(Salary).where(Salary.employee_id == user.employee_id)
    ).all()
    return {
        "records": [r.to_dict() for r in rows],
        "range_start": "",
        "range_end": "",
    }


class SalaryUpsert(BaseModel):
    """管理者编辑工资核算（9 字段全量更新，performance_rating 为系数）。"""
    no: int | None = None
    name: str | None = None
    position: str | None = None
    base_salary: float = 0
    performance_rating: float = 1.0       # 绩效系数 (DECIMAL 3,2)
    performance_bonus: float = 0
    allowance: float = 0
    gross_salary: float = 0


@router.put("/{emp_id}")
async def upsert_salary(emp_id: str, body: SalaryUpsert,
                        manager: Employee = Depends(require_manager),
                        db: Session = Depends(get_db)):
    emp = db.scalar(select(Employee).where(Employee.employee_id == int(emp_id)))
    if not emp:
        return {"error": f"工号 {emp_id} 不存在"}
    rec = db.scalar(select(Salary).where(Salary.employee_id == emp_id))
    if not rec:
        rec = Salary(employee_id=emp_id)
        db.add(rec)
    rec.no = body.no if body.no is not None else emp.no
    rec.name = body.name if body.name is not None else emp.name
    rec.position = body.position if body.position is not None else emp.position
    rec.base_salary = body.base_salary
    rec.performance_rating = body.performance_rating
    rec.performance_bonus = body.performance_bonus
    rec.allowance = body.allowance
    rec.gross_salary = body.gross_salary
    db.commit()
    return rec.to_dict()


@router.get("/report")
async def salary_report(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    manager: Employee = Depends(require_manager),
    db: Session = Depends(get_db),
):
    start, end = _salary_period_range(period, target_month)
    perms = set(manager.permission_list)
    emps = db.scalars(select(Employee)).all()
    if len(perms) >= 5:
        visible = {e.employee_id: e for e in emps}
    else:
        visible = {e.employee_id: e for e in emps
                   if e.position in perms or e.employee_id == manager.employee_id}
    # 工资表为静态快照（每人一条），无 created_at 时间戳，
    # period 参数保留兼容前端统一筛选 UI，但不做时间过滤。
    cond = [Salary.employee_id.in_(visible.keys())]
    rows = db.scalars(select(Salary).where(*cond)).all()
    totals = [r.gross_salary for r in rows]
    stats = {
        "slip_count": len(rows),
        "total_payroll": sum(totals),
        "avg_pay": sum(totals) / len(totals) if totals else 0,
    }
    return {
        "period": period,
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
        "rows": [{**r.to_dict(), "employee_name": r.name} for r in rows],
        "stats": stats,
    }
