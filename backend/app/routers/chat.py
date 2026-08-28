"""智能助手对话入口 —— WF-1 意图识别 + 后端动作分发。

Dify 只负责「听懂」，业务数据永远由后端接口提供（契约硬规则）。
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import WORK_START
from ..database import get_db
from ..dify_client import wf1_intent, dify_status
from ..models import Attendance, Employee, Reimbursement, Salary
from ..security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["智能助手"])


class ChatIn(BaseModel):
    message: str


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if hasattr(dt, "strftime") else str(dt)[11:16]


def _reply_attendance(user, db, action, params) -> str:
    period = params.get("period", "week")
    today = date.today()
    if period == "month":
        start, label = today.replace(day=1), "本月"
    else:
        start, label = today - timedelta(days=today.weekday()), "本周"
    rows = db.scalars(select(Attendance).where(
        Attendance.employee_id == user.id, Attendance.work_date >= start,
    ).order_by(Attendance.checkin_time)).all()
    if action == "checkin":
        return ("打卡请在「考勤打卡」页面点击按钮操作，我可以帮你查询记录。"
                f"{label}已有 {len(rows)} 条打卡记录。")
    if not rows:
        return f"{label}还没有打卡记录哦，去「考勤打卡」页面打个卡吧。"
    late = sum(1 for r in rows if r.is_late)
    lines = [f"{r.work_date} {'上班' if r.type == 'clock_in' else '下班'} {_fmt_time(r.checkin_time)}"
             + ("（迟到）" if r.is_late else "") for r in rows]
    return f"{label}共 {len(rows)} 条打卡记录，迟到 {late} 次：\n" + "\n".join(lines[:10])


def _reply_reimbursement(user, db) -> str:
    rows = db.scalars(select(Reimbursement).where(
        Reimbursement.employee_id == user.id,
    ).order_by(Reimbursement.submit_time.desc())).all()
    status_cn = {"draft": "草稿", "submitted": "待审批", "approving": "审批中",
                 "approved": "已通过", "rejected": "已驳回"}
    if not rows:
        return "你还没有报销记录。需要提交的话请到「费用报销」页面上传材料。"
    lines = [f"#{r.id} {r.category or '未填类目'} {r.amount:.2f}元 · {status_cn.get(r.status, r.status)}"
             for r in rows[:8]]
    return f"你有 {len(rows)} 条报销记录：\n" + "\n".join(lines)


def _reply_salary(user, db) -> str:
    rows = db.scalars(select(Salary).where(
        Salary.id == user.emp_id,
    )).all()
    if not rows:
        return "还没有工资核算记录。到「工资核算」页面提交绩效达成情况即可生成。"
    r = rows[0]
    return (f"最新工资核算（工号 {r.id} {r.name}）：基本 {r.base_salary:.0f} + 绩效奖金 {r.performance_bonus:.0f} + "
            f"津贴 {r.allowance:.0f} = 应发 {r.gross_salary:.0f} 元（评级 {r.performance_rating}）。")


def _reply_assessment(user, db, params) -> str:
    pos = params.get("position", "")
    if pos:
        return f"好的，「{pos}」的详细岗位介绍请到「进阶考核」页面查看，这里为你做个跳转参考。"
    return "想了解哪个岗位？告诉我岗位名，或到「进阶考核」页面查询岗位介绍与能力要求。"


@router.post("")
async def chat(body: ChatIn, user: Employee = Depends(get_current_user),
               db: Session = Depends(get_db)):
    intent = await wf1_intent(body.message, str(user.emp_id))
    module, action, params = intent.get("module", "chat"), intent.get("action", "reply"), intent.get("params", {})

    if module == "attendance":
        reply = _reply_attendance(user, db, action, params)
    elif module == "reimbursement":
        reply = _reply_reimbursement(user, db)
    elif module == "salary":
        reply = _reply_salary(user, db)
    elif module == "assessment":
        reply = _reply_assessment(user, db, params)
    else:
        reply = ("我可以帮你处理考勤打卡、费用报销、工资核算、进阶考核这几类事务，"
                 "例如：「我这个月迟到几次了」「我的报销到哪一步了」「查一下调度经理的岗位要求」。")
    return {"reply": reply, "module": module, "action": action}


@router.get("/status")
def ai_status(user: Employee = Depends(get_current_user)):
    """AI 大脑接入状态（前端展示用）。"""
    return {"dify": dify_status()}
