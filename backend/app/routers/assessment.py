from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..local_rules import wf4_fallback
from ..models import AssessmentLog, Employee
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
    db.add(AssessmentLog(employee_id=user.id, position_queried=position))
    db.commit()
    return result


@router.get("/stats")
def stats(manager: Employee = Depends(require_manager),
          db: Session = Depends(get_db)):
    rows = db.execute(
        select(AssessmentLog.position_queried, Employee.name, func.count(AssessmentLog.id))
        .join(Employee, AssessmentLog.employee_id == Employee.id)
        .group_by(AssessmentLog.position_queried, Employee.name)
        .order_by(func.count(AssessmentLog.id).desc())
    ).all()
    return {"rows": [
        {"name": r[1], "position_queried": r[0], "count": r[2]} for r in rows
    ]}
