from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee
from ..security import create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginIn(BaseModel):
    emp_id: int
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    emp = db.scalar(select(Employee).where(Employee.employee_id == body.emp_id))
    if not emp or not verify_password(body.password, emp.password_hash):
        raise HTTPException(401, "工号或密码错误")
    return {
        "token": create_token(emp),
        "role": emp.role,
        "name": emp.name,
        "emp_id": emp.employee_id,
        "department": emp.department,
        "position": emp.position,
        "permissions": emp.permission_list,
    }
