"""本地规则层（无 Dify / 无外部 AI 依赖）。

历史：原本所有 AI 能力都通过 dify_client.py 调用 Dify 工作流（WF-1~WF-5 及各业务分析）。
2026-08-29 起，散落的 AI 分析全部移除——AI 能力统一收敛到右下角「智能助手」气泡
（/api/chat）一个入口，将来由单个「集合所有工作流」的统一智能体承接。

本文件只保留纯本地的兜底逻辑，保证不依赖任何外部 AI 也能正常运行：
- 气泡关键词路由（意图识别的本地版）
- 绩效打分本地规则（工资核算兜底）
- 岗位知识本地模板（进阶考核兜底）
"""
import re

# ============================================================
# 气泡关键词路由（WF-1 意图识别的本地版）
# ============================================================
_WF1_RULES = [
    (("打卡", "签到", "上班卡", "下班卡"), "attendance", "checkin"),
    (("迟到", "考勤", "出勤", "我的记录"), "attendance", "query_my"),
    (("报销", "发票", "票据"), "reimbursement", "query_my"),
    (("工资", "薪资", "工资条", "绩效"), "salary", "query_my"),
    (("岗位", "转岗", "升职", "晋升", "考核"), "assessment", "query"),
]


def wf1_fallback(user_message: str) -> dict:
    """纯本地意图识别：关键词 → (module, action, params)。"""
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


# ============================================================
# 绩效本地打分（工资核算兜底）
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
        "reasoning": "（本地规则评估）依据关键词完成度评估。",
    }


# ============================================================
# 岗位知识本地模板（进阶考核兜底）
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
        ),
        "skills": t["skills"],
        "management_abilities": t["management_abilities"],
        "suggested_path": t["suggested_path"],
    }
