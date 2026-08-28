from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import BASE_SALARY_MAP, BASE_SALARY_DEFAULT, SUBSIDY_DEFAULT, PERFORMANCE_RATIO
from ..database import get_db
from ..dify_client import wf3_performance, wf5_analysis
from ..models import Employee, Salary
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/salary", tags=["工资"])


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
    base = float(BASE_SALARY_MAP.get(user.position, BASE_SALARY_DEFAULT))
    perf_base = base * PERFORMANCE_RATIO
    performance = round(perf_base * score / 100, 2)
    subsidy = SUBSIDY_DEFAULT
    total = round(base + performance + subsidy, 2)
    period = f"{date.today():%Y-%m}"

    rec = db.scalar(select(Salary).where(
        Salary.employee_id == user.id, Salary.period == period))
    if rec:  # 同月重复提交 → 覆盖
        rec.base, rec.performance, rec.subsidy, rec.total = base, performance, subsidy, total
        rec.performance_input = body.achievements
    else:
        rec = Salary(employee_id=user.id, period=period, base=base,
                     performance=performance, subsidy=subsidy, total=total,
                     performance_input=body.achievements)
        db.add(rec)
    db.commit()
    return {
        **rec.to_dict(),
        "performance_score": score,
        "reasoning": result.get("reasoning", ""),
        "name": user.name, "position": user.position,
    }


@router.get("/my")
def my_salary(user: Employee = Depends(get_current_user),
              db: Session = Depends(get_db)):
    rows = db.scalars(select(Salary).where(
        Salary.employee_id == user.id,
    ).order_by(Salary.period.desc())).all()
    return {"records": [r.to_dict() for r in rows]}


@router.get("/report")
async def salary_report(manager: Employee = Depends(require_manager),
                        db: Session = Depends(get_db)):
    perms = set(manager.permission_list)
    emps = db.scalars(select(Employee)).all()
    if len(perms) >= 5:
        visible = {e.id: e for e in emps}
    else:
        visible = {e.id: e for e in emps if e.position in perms or e.id == manager.id}
    rows = db.scalars(select(Salary).where(
        Salary.employee_id.in_(visible.keys()),
    ).order_by(Salary.period.desc())).all()
    totals = [r.total for r in rows]
    stats = {
        "slip_count": len(rows),
        "total_payroll": sum(totals),
        "avg_pay": sum(totals) / len(totals) if totals else 0,
    }
    analysis = await wf5_analysis("salary", f"{date.today():%Y-%m}", stats, str(manager.emp_id))
    return {
        "rows": [{**r.to_dict(), "employee_name": visible[r.employee_id].name if r.employee_id in visible else "",
                  "position": visible[r.employee_id].position if r.employee_id in visible else ""}
                 for r in rows],
        "stats": stats,
        "analysis": analysis,
    }
