"""智能助手对话入口 —— 统一由 Dify Agent 承接（attendance_ask 入口）。"""
from fastapi import APIRouter, Depends

from ..config import DIFY_AGENT_KEY
from ..security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["智能助手"])


@router.get("/status")
def ai_status(user=Depends(get_current_user)):
    """AI 能力接入状态（前端展示用）。"""
    return {"dify": {"enabled": bool(DIFY_AGENT_KEY),
                     "note": "统一智能体已接入" if DIFY_AGENT_KEY else "等待配置 API Key"}}
