from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..local_rules import wf4_fallback
from ..models import AssessmentLog, AssessmentStat, Employee
from ..security import get_current_user, require_manager

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
    db.add(AssessmentLog(employee_id=user.employee_id, position_queried=position))
    db.commit()
    return result


@router.get("/stats")
def stats(manager: Employee = Depends(require_manager),
          db: Session = Depends(get_db)):
    rows = db.execute(
        select(AssessmentLog.position_queried, Employee.name, func.count(AssessmentLog.id))
        .join(Employee, AssessmentLog.employee_id == Employee.employee_id)
        .group_by(AssessmentLog.position_queried, Employee.name)
        .order_by(func.count(AssessmentLog.id).desc())
    ).all()
    return {"rows": [
        {"name": r[1], "position_queried": r[0], "count": r[2]} for r in rows
    ]}


@router.get("/scores")
def my_scores(user: Employee = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """本人考核成绩（原岗位 / 意向岗位 / 成绩 / 测试时间）。"""
    rows = db.execute(
        select(AssessmentStat, Employee.name)
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id)
        .where(AssessmentStat.employee_id == user.employee_id)
        .order_by(AssessmentStat.test_time.desc())
    ).all()
    return {"scores": [{"name": r[1], **r[0].to_dict()} for r in rows]}


@router.get("/scores/all")
def all_scores(manager: Employee = Depends(require_manager),
               db: Session = Depends(get_db)):
    """管理员：全员考核成绩汇总（按工号、测试时间倒序）。"""
    rows = db.execute(
        select(AssessmentStat, Employee.name)
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id)
        .order_by(AssessmentStat.employee_id, AssessmentStat.test_time.desc())
    ).all()
    return {"scores": [{"name": r[1], **r[0].to_dict()} for r in rows]}
