from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import BASE_SALARY_MAP, BASE_SALARY_DEFAULT, SUBSIDY_DEFAULT, PERFORMANCE_RATIO
from ..database import get_db
from ..dify_client import wf3_performance, wf5_analysis
from ..models import Employee, Salary
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/salary", tags=["工资"])


def _rating(score: float) -> str:
    """绩效分数 → 评级。"""
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


class PerformanceIn(BaseModel):
    achievements: str


@router.post("/submit-performance")
async def submit_performance(body: PerformanceIn,
                             user: Employee = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    if not body.achievements.strip():
        return {"error": "achievements 不能为空"}
    # WF-3：AI 抽取绩效（未接入时走本地规则）
    result = await wf3_performance(
        {"emp_id": user.emp_id, "name": user.name,
         "position": user.position, "department": user.department},
        body.achievements, str(user.emp_id),
    )
    score = float(result.get("performance_score", 60))
    base_salary = float(BASE_SALARY_MAP.get(user.position, BASE_SALARY_DEFAULT))
    perf_bonus = round(base_salary * PERFORMANCE_RATIO * score / 100, 2)
    allowance = SUBSIDY_DEFAULT
    gross = round(base_salary + perf_bonus + allowance, 2)
    rating = _rating(score)
    period = f"{date.today():%Y-%m}"

    rec = db.scalar(select(Salary).where(
        Salary.emp_id == user.emp_id, Salary.period == period))
    if rec:  # 同月重复提交 → 覆盖
        rec.no, rec.emp_id, rec.name, rec.position = user.no, user.emp_id, user.name, user.position
        rec.base_salary, rec.performance_rating = base_salary, rating
        rec.performance_bonus, rec.allowance, rec.gross_salary = perf_bonus, allowance, gross
    else:
        rec = Salary(
            no=user.no, emp_id=user.emp_id, name=user.name, position=user.position,
            base_salary=base_salary, performance_rating=rating,
            performance_bonus=perf_bonus, allowance=allowance,
            gross_salary=gross, period=period,
        )
        db.add(rec)
    db.commit()
    return {
        **rec.to_dict(),
        "performance_score": score,
        "reasoning": result.get("reasoning", ""),
    }


@router.get("/my")
def my_salary(user: Employee = Depends(get_current_user),
              db: Session = Depends(get_db)):
    rows = db.scalars(select(Salary).where(
        Salary.emp_id == user.emp_id,
    ).order_by(Salary.period.desc())).all()
    return {"records": [r.to_dict() for r in rows]}


@router.get("/report")
async def salary_report(manager: Employee = Depends(require_manager),
                        db: Session = Depends(get_db)):
    perms = set(manager.permission_list)
    emps = db.scalars(select(Employee)).all()
    if len(perms) >= 5:
        visible = {e.emp_id: e for e in emps}
    else:
        visible = {e.emp_id: e for e in emps
                   if e.position in perms or e.emp_id == manager.emp_id}
    rows = db.scalars(select(Salary).where(
        Salary.emp_id.in_(visible.keys()),
    ).order_by(Salary.period.desc())).all()
    totals = [r.gross_salary for r in rows]
    stats = {
        "slip_count": len(rows),
        "total_payroll": sum(totals),
        "avg_pay": sum(totals) / len(totals) if totals else 0,
    }
    analysis = await wf5_analysis("salary", f"{date.today():%Y-%m}", stats, str(manager.emp_id))
    return {
        "rows": [r.to_dict() for r in rows],
        "stats": stats,
        "analysis": analysis,
    }
