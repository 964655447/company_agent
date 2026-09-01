"""Dify 统一智能体适配层。

所有需要「AI 大脑」的入口（右下角气泡 / 智能助手聊天页）都走这里，
统一负责：
  - 流式调用 Dify Agent 的 /chat-messages
  - 拼接流式增量（Dify Agent 会既发增量又发全量，需去重）
  - 无 Key / 网络异常时返回 ("", False, None)，由调用方降级到本地兜底

调用方只需传入当前登录员工与用户问题，员工身份 + 权限范围会自动作为
`inputs` 带给 Dify，使 Agent 能做「权限感知」的回答
（例如只能查自己/自己权限范围内的数据）。

注意：本项目的员工标识统一用 `employee_id`（工号，如 220401），
数据库里的 employees.id 只是内部自增主键，不要混用。
"""
import json

import httpx

from .config import DIFY_AGENT_KEY, DIFY_BASE_URL


def _user_inputs(user) -> dict:
    """把当前员工身份 + 权限范围整理成 Dify 的 inputs。

    权限来自花名册 `permissions` 字段（可访问的岗位范围列表）。
    """
    return {
        "id": str(user.id),                      # 内部员工ID（数据库主键，仅供关联）
        "employee_id": str(user.employee_id),    # 员工工号/登录账号
        "emp_name": user.name,
        "department": user.department,
        "position": user.position,
        "role": user.role,                       # manager / employee
        "permissions": ",".join(user.permission_list),
    }


def _identity_context(user) -> str:
    """把员工身份拼成一段系统上下文，直接放在用户问题前面。

    部分 Dify Agent 无法正确替换 Prompt 里的 {{employee_id}} 等变量，
    把身份信息明文拼进 query 可以让模型稳定识别当前用户是谁。
    """
    perms = ",".join(user.permission_list) or "无"
    return (
        "【当前登录员工信息】\n"
        f"员工ID（内部编号）：{user.id}\n"
        f"工号（登录账号）：{user.employee_id}\n"
        f"姓名：{user.name}\n"
        f"部门：{user.department}\n"
        f"岗位：{user.position}\n"
        f"角色：{user.role}\n"
        f"可查询岗位范围：{perms}\n"
        "注意：\"员工ID\"指内部编号，\"工号\"指登录账号/员工号码，两者不同，回答时不要混淆。\n"
        "以上信息仅用于辅助理解用户问题，不要直接复述给用户。\n\n"
        "【用户问题】\n"
    )


async def stream_dify_agent(user, query: str,
                             conversation_id: str | None = None,
                             files: list[str] | None = None):
    """流式版：逐增量 yield {"text": 增量文本, "conv_id": 会话id, "ai": 是否走AI}。

    调用方（/api/chat 等）可把每个 delta 直接转发给前端做逐字渲染。
    - 无 Key 或任意异常时 yield 一次 {"ai": False} 即结束，由调用方降级兜底。
    - Dify Agent 流式响应里 answer 可能既发增量又发全量（全量 chunk 会把前面
      内容整段重发），这里负责去重，只 yield 真正新增的那段文本。
    """
    if not DIFY_AGENT_KEY:
        yield {"text": "", "conv_id": conversation_id, "ai": False}
        return
    conv_id = conversation_id
    try:
        # 把身份信息直接拼进 query，避免依赖 Dify 的变量替换机制
        enriched_query = _identity_context(user) + (query or "")
        payload = {
            "query": enriched_query,
            "response_mode": "streaming",
            "user": str(user.employee_id),
            # 员工身份 + 权限范围作为 inputs 带给 Dify（权限感知）。
            # 首次（无 conversation_id）时 Dify 把它绑定到会话；后续续会话时
            # Dify 会沿用该会话的身份，inputs 被忽略也没关系。
            "inputs": _user_inputs(user),
            "auto_generate_name": False,
        }
        if conv_id:
            payload["conversation_id"] = conv_id
        # 文件（阅卷工作流用）：files 为已上传拿到的 upload_file_id 列表
        if files:
            payload["files"] = [
                {"type": "document", "transfer_method": "local_file",
                 "upload_file_id": fid}
                for fid in files
            ]

        async with httpx.AsyncClient(timeout=httpx.Timeout(100.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{DIFY_BASE_URL.rstrip('/')}/chat-messages",
                headers={
                    "Authorization": f"Bearer {DIFY_AGENT_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                parts = []  # 已累加文本，用于增量去重
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    cid = chunk.get("conversation_id")
                    if cid:
                        conv_id = cid
                    content = chunk.get("answer") or ""
                    if not content:
                        continue
                    # 去重：保留真正新增的那段
                    prev = "".join(parts)
                    if prev and content.startswith(prev):
                        new_text = content[len(prev):] if len(content) > len(prev) else ""
                        parts = [content]
                    elif prev:
                        ov = 0
                        for i in range(1, min(len(prev), len(content)) + 1):
                            if prev.endswith(content[:i]):
                                ov = i
                        new_text = content[ov:]
                        parts.append(content[ov:])
                    else:
                        new_text = content
                        parts.append(content)
                    if new_text:
                        yield {"text": new_text, "conv_id": conv_id, "ai": True}
    except Exception:
        # Dify 不可用（Key 无效 / 服务挂了 / 超时）一律降级
        yield {"text": "", "conv_id": conversation_id, "ai": False}


async def call_dify_agent(user, query: str,
                          conversation_id: str | None = None,
                          files: list[str] | None = None) -> tuple[str, bool, str | None]:
    """兼容旧调用（考勤等）：聚合流式结果为完整字符串后返回。

    返回 (回答文本, 是否走AI, conversation_id)。无 Key / 异常时返回
    ("", False, conversation_id)，由调用方降级兜底。
    """
    acc, ai, conv_id = "", False, conversation_id
    async for ev in stream_dify_agent(user, query, conversation_id, files):
        if ev["ai"]:
            ai = True
            acc += ev["text"]
        if ev["conv_id"]:
            conv_id = ev["conv_id"]
    if ai:
        return (acc.strip() or "智能体未返回内容", True, conv_id)
    return "", False, conv_id


def upload_dify_file(content: bytes, filename: str) -> str | None:
    """把文件上传到 Dify 拿 upload_file_id（供工作流/智能体引用）。

    返回 file_id 字符串；无 Key / 上传失败返回 None（调用方按降级处理）。
    Dify 文档类文件统一用 multipart 字段名 `file`。
    """
    if not DIFY_AGENT_KEY:
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{DIFY_BASE_URL.rstrip('/')}/files/upload",
                headers={"Authorization": f"Bearer {DIFY_AGENT_KEY}"},
                files={"file": (filename or "upload.bin", content)},
            )
            resp.raise_for_status()
            return resp.json().get("id")
    except Exception:
        return None
