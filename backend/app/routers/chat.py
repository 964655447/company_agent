"""智能助手对话入口 —— 统一由 Dify Agent 承接。
- GET  /api/chat/status : 前端展示 AI 接入状态
- POST /api/chat        : 统一对话入口（右下角气泡与「智能助手」页共用同一智能体）
- POST /api/chat/file   : 带文件入口（阅卷工作流用）
两个 POST 均返回 SSE 流式响应（text/event-stream），前端逐字渲染。
"""
import json

from fastapi import APIRouter, Depends, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import DIFY_AGENT_KEY
from ..database import get_db
from ..dify_client import stream_dify_agent, upload_dify_file
from ..local_rules import wf1_fallback
from ..routers.attendance import _local_fallback as attendance_fallback
from ..security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["智能助手"])


class ChatIn(BaseModel):
    message: str = ""
    conversation_id: str | None = None   # 续会话用：回传上一次的会话 id


def _sse(event: str, data: str) -> str:
    """构造一条 SSE 事件。

    按 SSE 规范：多行 data 用多个 `data:` 行承载（前端会按 \\n 拼接回原文），
    避免 delta 文本里的换行被截断。
    """
    lines = [f"event: {event}"] + [f"data: {ln}" for ln in (data or "").split("\n")]
    return "\n".join(lines) + "\n\n"


def _fallback_reply(query: str, user, db) -> str:
    """Dify 不可用时的本地降级回复。"""
    if wf1_fallback(query)["module"] == "attendance":
        return attendance_fallback(query, user, db)
    return ("智能助手尚未接入（请在 backend/.env 配置 DIFY_AGENT_KEY，"
            "并在 Dify 中将「考核报告 / 岗位出题 / 阅卷」工作流发布为统一智能体的工具）")


@router.get("/status")
def ai_status(user=Depends(get_current_user)):
    """AI 能力接入状态（前端展示用）。"""
    return {"dify": {"enabled": bool(DIFY_AGENT_KEY),
                     "note": "统一智能体已接入" if DIFY_AGENT_KEY else "等待配置 API Key"}}


@router.post("")
async def chat(body: ChatIn, user=Depends(get_current_user), db=Depends(get_db)):
    """统一对话入口（SSE 流式）：转给 Dify 统一智能体，增量转发给前端。

    悬浮球与「智能助手」页共用。所有功能（考勤/考核报告/岗位出题/阅卷/自由问答）
    集合到这一个智能体，由 Dify 内部路由到对应工作流工具。
    支持 conversation_id：首轮不传，Dify 在流式响应里返回新会话 id，通过
    `meta` 事件回传前端，前端保存后回传即可跨轮次"记得住"上下文与身份。
    """
    query = (body.message or "").strip() or "你好"
    conv_id = body.conversation_id

    async def gen():
        nonlocal conv_id
        ai_ok = False
        async for ev in stream_dify_agent(user, query, conv_id, None):
            if not ev["ai"]:
                break                       # Dify 不可用 → 走降级
            ai_ok = True
            if ev["conv_id"]:
                conv_id = ev["conv_id"]
            if ev["text"]:
                yield _sse("delta", ev["text"])
        if ai_ok:
            yield _sse("meta", json.dumps({"conversation_id": conv_id, "ai": True}))
            yield _sse("done", "")
        else:
            yield _sse("meta", json.dumps({"conversation_id": conv_id, "ai": False}))
            yield _sse("delta", _fallback_reply(query, user, db))
            yield _sse("done", "")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/file")
async def chat_file(message: str = Form(""),
                    conversation_id: str = Form(None),
                    file: UploadFile = File(None),
                    user=Depends(get_current_user),
                    db=Depends(get_db)):
    """带文件的上传入口（阅卷工作流用）：先把试卷传到 Dify 拿 file_id，
    再随消息交给统一智能体（SSE 流式返回），由阅卷工作流工具引用该文件批改。

    降级（未配置 Key / 无文件）：直接以 SSE 形式返回提示，前端渲染一致。
    """
    if not DIFY_AGENT_KEY:
        return _sse_fallback("阅卷功能尚未接入（请在 backend/.env 配置 DIFY_AGENT_KEY，"
                             "并在 Dify 中发布「阅卷」工作流为统一智能体的工具）", conversation_id)
    if not file:
        return _sse_fallback("请先选择要批改的试卷文件（Word 文档）", conversation_id)

    content = await file.read()
    fid = upload_dify_file(content, file.filename or "paper.docx")
    query = message or "请批改这份员工试卷"
    conv_id = conversation_id

    async def gen():
        nonlocal conv_id
        ai_ok = False
        async for ev in stream_dify_agent(user, query, conv_id, [fid] if fid else None):
            if not ev["ai"]:
                break
            ai_ok = True
            if ev["conv_id"]:
                conv_id = ev["conv_id"]
            if ev["text"]:
                yield _sse("delta", ev["text"])
        if ai_ok:
            yield _sse("meta", json.dumps({"conversation_id": conv_id, "ai": True}))
            yield _sse("done", "")
        else:
            yield _sse("meta", json.dumps({"conversation_id": conv_id, "ai": False}))
            yield _sse("delta", "阅卷未返回内容。请确认：① 已在 backend/.env 配置正确的 "
                                 "DIFY_AGENT_KEY；② Dify「阅卷」工作流已发布为统一智能体工具且服务可达。")
            yield _sse("done", "")

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse_fallback(text: str, conversation_id: str | None):
    """未配置 Key / 参数缺失时的降级 SSE 响应（与正常流式前端解析一致）。"""
    async def gen():
        yield _sse("meta", json.dumps({"conversation_id": conversation_id, "ai": False}))
        yield _sse("delta", text)
        yield _sse("done", "")
    return StreamingResponse(gen(), media_type="text/event-stream")
