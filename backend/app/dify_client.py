"""Dify 适配层（AI 大脑的唯一入口）。

- 已配置 DIFY_BASE_URL + 对应 API Key：走真实工作流（契约见 contracts/dify-io.md）。
- 未配置：抛 DifyNotConfigured，由各路由降级到本地 fallback 规则，系统照常可用。
- 后续接 Dify 时只需在 backend/.env 填 5 个 Key，业务代码零改动。
"""
import json
import re
from typing import Any

import httpx

from . import config


class DifyNotConfigured(Exception):
    """Dify 未接入或对应工作流未配置 Key。"""


async def run_workflow(key: str, inputs: dict, user: str) -> dict:
    """统一调用 POST /v1/workflows/run（阻塞），返回 data.outputs。"""
    if not (config.DIFY_BASE_URL and key):
        raise DifyNotConfigured()
    payload = {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": f"emp-{user}",
    }
    async with httpx.AsyncClient(timeout=config.DIFY_TIMEOUT) as client:
        resp = await client.post(
            f"{config.DIFY_BASE_URL.rstrip('/')}/v1/workflows/run",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    outputs = data.get("outputs", {})
    # Dify 直接回复可能是 JSON 字符串（约定必须返回 JSON），做一次宽容解析
    if isinstance(outputs, str):
        try:
            outputs = json.loads(outputs)
        except json.JSONDecodeError:
            outputs = {"text": outputs}
    for v in outputs.values():
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    outputs.update(parsed)
            except json.JSONDecodeError:
                pass
    return outputs


# ============================================================
# WF-1 身份意图识别（fallback：关键词路由）
# ============================================================
_WF1_RULES = [
    (("打卡", "签到", "上班卡", "下班卡"), "attendance", "checkin"),
    (("迟到", "考勤", "出勤", "我的记录"), "attendance", "query_my"),
    (("报销", "发票", "票据"), "reimbursement", "query_my"),
    (("工资", "薪资", "工资条", "绩效"), "salary", "query_my"),
    (("岗位", "转岗", "升职", "晋升", "考核"), "assessment", "query"),
]


def wf1_fallback(user_message: str) -> dict:
    msg = user_message or ""
    for keys, module, action in _WF1_RULES:
        if any(k in msg for k in keys):
            params = {}
            if "月" in msg:
                params["period"] = "month"
            elif "周" in msg or "本周" in msg:
                params["period"] = "week"
            return {"module": module, "action": action, "params": params}
    return {"module": "chat", "action": "reply", "params": {}}


async def wf1_intent(user_message: str, user: str) -> dict:
    try:
        out = await run_workflow(config.DIFY_KEY_WF1, {"user_message": user_message}, user)
        if "module" in out:
            return out
    except DifyNotConfigured:
        pass
    except Exception:
        pass
    return wf1_fallback(user_message)


# ============================================================
# WF-3 绩效抽取与工资计算（fallback：规则打分）
# ============================================================
_POSITIVE_WORDS = ["完成", "达成", "超额", "回款", "大单", "客户", "好评", "满意", "零投诉", "提前", "优化", "提升"]
_NEGATIVE_WORDS = ["未完成", "延期", "投诉", "失误", "欠缺", "未达成"]


def wf3_fallback(achievements: str) -> dict:
    text = achievements or ""
    score = 60.0
    hits = sum(1 for w in _POSITIVE_WORDS if w in text)
    score += min(hits * 6, 30)
    negs = sum(1 for w in _NEGATIVE_WORDS if w in text)
    score -= negs * 8
    # 提到百分比/数字额外加分
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    for n in nums:
        score += min(float(n) / 20, 5)
    score = max(50.0, min(95.0, score))
    return {
        "performance_score": round(score, 1),
        "reasoning": "（本地规则评估）依据关键词完成度评估；接入 Dify 后将由 AI 依据具体描述打分。",
    }


async def wf3_performance(emp: dict, achievements: str, user: str) -> dict:
    try:
        out = await run_workflow(
            config.DIFY_KEY_WF3,
            {
                "emp_id": emp["emp_id"], "employee_name": emp["name"],
                "position": emp["position"], "department": emp["department"],
                "achievements": achievements,
            },
            user,
        )
        if "performance_score" in out:
            return out
    except DifyNotConfigured:
        pass
    except Exception:
        pass
    return wf3_fallback(achievements)


# ============================================================
# WF-4 岗位知识 RAG（fallback：内置岗位知识）
# ============================================================
_KNOWLEDGE_TEMPLATES = {
    "default": {
        "skills": ["业务熟练度", "沟通协调", "流程规范", "数据意识"],
        "management_abilities": ["团队协作", "任务拆解", "异常反馈"],
        "suggested_path": ["先在本岗位连续 2 个考核周期达标", "再申请参与跨部门项目", "最后竞聘目标岗位"],
    }
}


def wf4_fallback(position: str) -> dict:
    t = _KNOWLEDGE_TEMPLATES["default"]
    return {
        "intro": (
            f"「{position}」是公司业务链条上的关键岗位，负责对应环节的执行与协同，"
            "需要对流程规范有完整把握，并与其他部门保持高效配合。"
            "（当前为本地内置知识，接入 Dify 知识库后将返回完整岗位说明。）"
        ),
        "skills": t["skills"],
        "management_abilities": t["management_abilities"],
        "suggested_path": t["suggested_path"],
    }


async def wf4_position(position: str, employee_name: str, user: str) -> dict:
    try:
        out = await run_workflow(
            config.DIFY_KEY_WF4, {"position": position, "employee_name": employee_name}, user
        )
        if out.get("intro"):
            return out
    except DifyNotConfigured:
        pass
    except Exception:
        pass
    return wf4_fallback(position)


# ============================================================
# WF-5 分析报告生成（fallback：模板文案；数字全部由后端统计传入）
# ============================================================
def wf5_fallback(report_type: str, stats: dict) -> str:
    if report_type == "attendance":
        return (
            f"本期共记录考勤 {stats.get('record_count', 0)} 人次，迟到 {stats.get('late_count', 0)} 人次。"
            + (f"迟到最多：{stats.get('late_top_str', '')}，建议主管约谈并优化通勤安排。" if stats.get("late_top_str") else "整体出勤情况良好，请保持。")
            + "（本地模板文案，接入 Dify 后将由 AI 生成更深入的行为分析。）"
        )
    if report_type == "reimbursement":
        return (
            f"本期报销申请 {stats.get('total_count', 0)} 笔，合计 {stats.get('total_amount', 0):.2f} 元，"
            f"待审批 {stats.get('pending_count', 0)} 笔。"
            f"单笔最高 {stats.get('max_amount', 0):.2f} 元，请关注是否存在异常大额报销。"
            "（本地模板文案，接入 Dify 后将由 AI 做异常模式分析。）"
        )
    if report_type == "salary":
        return (
            f"本期工资总额 {stats.get('total_payroll', 0):.2f} 元，共 {stats.get('slip_count', 0)} 张工资条，"
            f"平均 {stats.get('avg_pay', 0):.2f} 元。"
            "（本地模板文案，接入 Dify 后将由 AI 做工资构成与稳定性分析。）"
        )
    return "暂无分析。"


async def wf5_analysis(report_type: str, period: str, stats: dict, user: str) -> str:
    try:
        out = await run_workflow(
            config.DIFY_KEY_WF5,
            {"report_type": report_type, "period": period, "stats_json": json.dumps(stats, ensure_ascii=False)},
            user,
        )
        if out.get("analysis"):
            return out["analysis"]
    except DifyNotConfigured:
        pass
    except Exception:
        pass
    return wf5_fallback(report_type, stats)


# ============================================================
# 用户自建「报销费用管理端」工作流（管理员报销 AI 分析）
# ============================================================
async def wf_reimb_report(emp_id: str, period: str, user: str) -> str:
    """调用用户自建「报销费用管理端」工作流，返回 AI 分析文案。

    输入变量：id（员工工号或 'all'）、time（周期，如 2026-08）。
    后端取 outputs 中第一个非空字符串值作为分析返回；未配置 Key / 调用失败返回空串，
    由调用方降级到本地 wf5_fallback 文案。
    """
    try:
        out = await run_workflow(config.DIFY_KEY_REIMB, {"id": emp_id, "time": period}, user)
        for v in out.values():
            if isinstance(v, str) and v.strip():
                return v
    except DifyNotConfigured:
        pass
    except Exception:
        pass
    return ""


# ============================================================
# 考勤类工作流（WF-6 考勤问答 / WF-7 员工打卡 / WF-8 管理端分析）
# 已于 2026-08-28 撤销：对应 Dify 工作流已删除，相关接口改为纯本地实现
# （见 routers/attendance.py 的 /ask、/command、/report）。
# ============================================================


def dify_status() -> dict:
    """给前端的 AI 接入状态展示。"""
    return {
        "base_url": bool(config.DIFY_BASE_URL),
        "wf1": bool(config.DIFY_KEY_WF1), "wf2": bool(config.DIFY_KEY_WF2),
        "wf3": bool(config.DIFY_KEY_WF3), "wf4": bool(config.DIFY_KEY_WF4),
        "wf5": bool(config.DIFY_KEY_WF5),
    }
