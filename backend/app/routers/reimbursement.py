import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dify_client import wf5_analysis
from ..models import Employee, Reimbursement

router = APIRouter(prefix="/api/reimbursement", tags=["费用报销"])


def _resolve_employee_id(db: Session, emp_id: str):
    """免鉴权调试模式：优先用传入工号解析员工，否则回退到库内首位员工。"""
    if emp_id:
        try:
            emp = db.scalar(select(Employee).where(Employee.emp_id == int(emp_id)))
            if emp:
                return emp.id
        except (ValueError, TypeError):
            pass
    first = db.scalar(select(Employee).order_by(Employee.id).limit(1))
    return first.id if first else None


@router.post("/submit")
async def submit(
    files: list[UploadFile] = File(default=[]),
    category: str = Form(""),
    amount: float = Form(0),
    desc: str = Form(""),
    emp_id: str = Form(""),
    db: Session = Depends(get_db),
):
    # 缺项检查（OCR 字段：amount/category/date；date 取提交当天视为有值）
    missing = []
    if not category.strip():
        missing.append("category")
    if not amount or amount <= 0:
        missing.append("amount")
    if not files:
        missing.append("files")

    ocr_raw = json.dumps({
        "category": category, "amount": amount, "desc": desc,
        "files": [f.filename for f in files],
    }, ensure_ascii=False)
    status = "draft" if missing else "submitted"

    eid = _resolve_employee_id(db, emp_id)
    rec = Reimbursement(employee_id=eid, category=category.strip(),
                        amount=amount or 0, ocr_raw=ocr_raw, status=status)
    db.add(rec)
    db.commit()
    return {
        "ticket_id": rec.id,
        "missing": missing,
        "status": status,
        "message": "材料缺失，已存草稿，补齐后请重新提交" if missing else "已提交审批",
    }


@router.get("/my")
def my_reimbursements(emp_id: str = "", db: Session = Depends(get_db)):
    q = select(Reimbursement)
    if emp_id:
        try:
            emp = db.scalar(select(Employee).where(Employee.emp_id == int(emp_id)))
            if emp:
                q = q.where(Reimbursement.employee_id == emp.id)
        except (ValueError, TypeError):
            pass
    rows = db.scalars(q.order_by(Reimbursement.submit_time.desc())).all()
    return {"records": [r.to_dict() for r in rows]}


class ReviewIn(BaseModel):
    action: str   # approve / reject


@router.post("/{ticket_id}/review")
def review(ticket_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    rec = db.get(Reimbursement, ticket_id)
    if not rec:
        raise HTTPException(404, "报销单不存在")
    if rec.status in ("approved", "rejected"):
        raise HTTPException(400, f"该单已处理（{rec.status}），不能重复审批")
    if body.action not in ("approve", "reject"):
        raise HTTPException(422, "action 必须为 approve 或 reject")
    rec.status = "approved" if body.action == "approve" else "rejected"
    rec.approver_id = None
    db.commit()
    return {"ticket_id": rec.id, "status": rec.status,
            "approver": "系统", "message": "已通过" if body.action == "approve" else "已驳回"}


@router.get("/report")
async def reimbursement_report(db: Session = Depends(get_db)):
    emps = db.scalars(select(Employee)).all()
    visible_ids = {e.id: e for e in emps}
    rows = db.scalars(select(Reimbursement).where(
        Reimbursement.employee_id.in_(visible_ids.keys()),
    ).order_by(Reimbursement.submit_time.desc())).all()

    pending = [r for r in rows if r.status in ("submitted", "approving")]
    amounts = [r.amount for r in rows]
    stats = {
        "total_count": len(rows),
        "pending_count": len(pending),
        "total_amount": sum(amounts),
        "max_amount": max(amounts) if amounts else 0,
    }
    analysis = await wf5_analysis("reimbursement", f"{__import__('datetime').date.today():%Y-%m}",
                                 stats, "")
    return {
        "rows": [{**r.to_dict(), "employee_name": visible_ids[r.employee_id].name if r.employee_id in visible_ids else ""}
                 for r in rows],
        "stats": stats,
        "analysis": analysis,
    }
