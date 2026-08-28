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

    rec = db.scalar(select(Salary).where(Salary.id == user.emp_id))
    if rec:  # 重复提交 → 覆盖本人工资核算
        rec.no, rec.name, rec.position = user.no, user.name, user.position
        rec.base_salary, rec.performance_rating = base_salary, rating
        rec.performance_bonus, rec.allowance, rec.gross_salary = perf_bonus, allowance, gross
    else:
        rec = Salary(
            id=user.emp_id, no=user.no, name=user.name, position=user.position,
            base_salary=base_salary, performance_rating=rating,
            performance_bonus=perf_bonus, allowance=allowance, gross_salary=gross,
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
        Salary.id == user.emp_id,
    )).all()
    return {"records": [r.to_dict() for r in rows]}


class SalaryUpsert(BaseModel):
    """管理者编辑工资核算（9 字段全量更新）。"""
    no: int | None = None
    name: str | None = None
    position: str | None = None
    base_salary: float = 0
    performance_rating: str = "C"
    performance_bonus: float = 0
    allowance: float = 0
    gross_salary: float = 0


@router.put("/{emp_id}")
async def upsert_salary(emp_id: int, body: SalaryUpsert,
                        manager: Employee = Depends(require_manager),
                        db: Session = Depends(get_db)):
    emp = db.scalar(select(Employee).where(Employee.emp_id == emp_id))
    if not emp:
        return {"error": f"工号 {emp_id} 不存在"}
    rec = db.scalar(select(Salary).where(Salary.id == emp_id))
    if not rec:
        rec = Salary(id=emp_id)
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
        Salary.id.in_(visible.keys()),
    )).all()
    totals = [r.gross_salary for r in rows]
    stats = {
        "slip_count": len(rows),
        "total_payroll": sum(totals),
        "avg_pay": sum(totals) / len(totals) if totals else 0,
    }
    analysis = await wf5_analysis("salary", f"{date.today():%Y-%m}", stats, str(manager.emp_id))
    return {
        "rows": [{**r.to_dict(), "employee_name": r.name} for r in rows],
        "stats": stats,
        "analysis": analysis,
    }
