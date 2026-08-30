"""智能助手对话入口 —— 统一由 Dify Agent 承接。
- GET  /api/chat/status : 前端展示 AI 接入状态
- POST /api/chat        : 统一对话入口（右下角气泡与「智能助手」页共用同一智能体）
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import DIFY_AGENT_KEY
from ..dify_client import call_dify_agent
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
async def chat(body: ChatIn, user=Depends(get_current_user)):
    """统一对话入口：转给 Dify 统一智能体（已携带员工身份/权限上下文）。

    支持 conversation_id：首轮不传，后端会从 Dify 流式响应里拿到会话 id
    并一并返回，前端保存后回传即可让智能体跨轮次"记得住"上下文与身份。
    """
    query = (body.message or "").strip() or "你好"
    answer, ai, conv_id = await call_dify_agent(user, query, body.conversation_id)
    if ai:
        return {"reply": answer, "ai": True, "module": "chat", "conversation_id": conv_id}
    return {"reply": "智能助手尚未接入（请在 backend/.env 配置 DIFY_AGENT_KEY）",
            "ai": False, "module": "chat", "conversation_id": conv_id}
