"""智能助手对话入口 —— 统一由 Dify Agent 承接。
- GET  /api/chat/status : 前端展示 AI 接入状态
- POST /api/chat        : 统一对话入口（右下角气泡与「智能助手」页共用同一智能体）
"""
from fastapi import APIRouter, Depends, Form, File, UploadFile
from pydantic import BaseModel

from ..config import DIFY_AGENT_KEY
from ..database import get_db
from ..dify_client import call_dify_agent, upload_dify_file
from ..local_rules import wf1_fallback
from ..routers.attendance import _local_fallback as attendance_fallback
from ..security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["智能助手"])


class ChatIn(BaseModel):
    message: str = ""
    conversation_id: str | None = None   # 续会话用：回传上一次的会话 id


@router.get("/status")
def ai_status(user=Depends(get_current_user)):
    """AI 能力接入状态（前端展示用）。"""
    return {"dify": {"enabled": bool(DIFY_AGENT_KEY),
                     "note": "统一智能体已接入" if DIFY_AGENT_KEY else "等待配置 API Key"}}


@router.post("")
async def chat(body: ChatIn, user=Depends(get_current_user), db=Depends(get_db)):
    """统一对话入口：转给 Dify 统一智能体（已携带员工身份/权限上下文）。

    悬浮球与「智能助手」页共用。所有功能（考勤/考核报告/岗位出题/阅卷/自由问答）
    集合到这一个智能体，由 Dify 内部路由到对应工作流工具。
    支持 conversation_id：首轮不传，后端会从 Dify 流式响应里拿到会话 id
    并一并返回，前端保存后回传即可让智能体跨轮次"记得住"上下文与身份。
    """
    query = (body.message or "").strip() or "你好"
    answer, ai, conv_id = await call_dify_agent(user, query, body.conversation_id)
    if ai:
        return {"reply": answer, "ai": True, "module": "chat", "conversation_id": conv_id}
    # 降级：考勤类问题走本地兜底（不依赖外部 AI）；其余提示待接入
    if wf1_fallback(query)["module"] == "attendance":
        return {"reply": attendance_fallback(query, user, db), "ai": False,
                "module": "attendance", "conversation_id": conv_id}
    return {"reply": "智能助手尚未接入（请在 backend/.env 配置 DIFY_AGENT_KEY，"
                     "并在 Dify 中将「考核报告 / 岗位出题 / 阅卷」工作流发布为统一智能体的工具）",
            "ai": False, "module": "chat", "conversation_id": conv_id}


@router.post("/file")
async def chat_file(message: str = Form(""),
                    conversation_id: str = Form(None),
                    file: UploadFile = File(None),
                    user=Depends(get_current_user),
                    db=Depends(get_db)):
    """带文件的上传入口（阅卷工作流用）：先把试卷传到 Dify 拿 file_id，
    再随消息交给统一智能体，由阅卷工作流工具引用该文件批改。

    降级（未配置 Key）：直接提示待接入，不上传、不报错。
    """
    if not DIFY_AGENT_KEY:
        return {"reply": "阅卷功能尚未接入（请在 backend/.env 配置 DIFY_AGENT_KEY，"
                         "并在 Dify 中发布「阅卷」工作流为统一智能体的工具）",
                "ai": False, "module": "grade", "conversation_id": conversation_id}
    if not file:
        return {"reply": "请先选择要批改的试卷文件（Word 文档）", "ai": False,
                "module": "grade", "conversation_id": conversation_id}
    content = await file.read()
    fid = upload_dify_file(content, file.filename or "paper.docx")
    answer, ai, conv_id = await call_dify_agent(
        user, message or "请批改这份员工试卷", conversation_id,
        files=[fid] if fid else None,
    )
    if not answer:
        return {"reply": "阅卷未返回内容。请确认：① 已在 backend/.env 配置正确的 DIFY_AGENT_KEY；"
                         "② Dify「阅卷」工作流已发布为统一智能体工具且服务可达。",
                "ai": False, "module": "grade", "conversation_id": conv_id}
    return {"reply": answer, "ai": ai, "module": "grade", "conversation_id": conv_id}
