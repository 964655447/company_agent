from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee
from ..security import get_current_user, hash_password, require_manager

router = APIRouter(prefix="/api/roster", tags=["花名册维护"])


class EmployeeIn(BaseModel):
    no: int | None = None
    emp_id: int
    name: str
    password: str | None = None        # 后端负责哈希，绝不入库明文
    permissions: list[str] = []
    position: str
    department: str


@router.get("")
def list_employees(manager: Employee = Depends(require_manager),
                    db: Session = Depends(get_db)):
    rows = db.scalars(select(Employee).order_by(Employee.no)).all()
    return {"records": [e.to_dict() for e in rows]}


@router.post("", status_code=201)
def add_employee(body: EmployeeIn, manager: Employee = Depends(require_manager),
                db: Session = Depends(get_db)):
    if not body.password:
        raise HTTPException(422, "新员工必须设置初始密码")
    if db.scalar(select(Employee).where(Employee.emp_id == body.emp_id)):
        raise HTTPException(400, f"工号 {body.emp_id} 已存在")
    if db.scalar(select(Employee).where(Employee.name == body.name)):
        raise HTTPException(400, f"姓名 {body.name} 已存在")
    max_no = db.scalar(select(Employee.no).order_by(Employee.no.desc()))
    emp = Employee(
        no=body.no if body.no else (max_no + 1 if max_no else 1),
        emp_id=body.emp_id, name=body.name,
        password_hash=hash_password(body.password),
        permissions=__import__("json").dumps(body.permissions, ensure_ascii=False),
        position=body.position, department=body.department,
    )
    db.add(emp)
    db.commit()
    return {"id": emp.id, **emp.to_dict()}


@router.put("/{emp_pk}")
def update_employee(emp_pk: int, body: EmployeeIn,
                    manager: Employee = Depends(require_manager),
                    db: Session = Depends(get_db)):
    emp = db.get(Employee, emp_pk)
    if not emp:
        raise HTTPException(404, "员工不存在")
    emp.emp_id, emp.name = body.emp_id, body.name
    emp.position, emp.department = body.position, body.department
    emp.permissions = __import__("json").dumps(body.permissions, ensure_ascii=False)
    if body.no:
        emp.no = body.no
    if body.password:  # 传了密码才更新（重置密码）
        emp.password_hash = hash_password(body.password)
    db.commit()
    return emp.to_dict()


@router.delete("/{emp_pk}", status_code=204)
def delete_employee(emp_pk: int, manager: Employee = Depends(require_manager),
                    db: Session = Depends(get_db)):
    emp = db.get(Employee, emp_pk)
    if not emp:
        raise HTTPException(404, "员工不存在")
    db.delete(emp)
    db.commit()
