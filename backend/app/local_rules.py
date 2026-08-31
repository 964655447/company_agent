"""本地规则层（无 Dify / 无外部 AI 依赖）。

历史：原本所有 AI 能力都通过 dify_client.py 调用 Dify 工作流（WF-1~WF-5 及各业务分析）。
2026-08-29 起，散落的 AI 分析全部移除——AI 能力统一收敛到右下角「智能助手」气泡
（/api/chat）一个入口，将来由单个「集合所有工作流」的统一智能体承接。

本文件只保留纯本地的兜底逻辑，保证不依赖任何外部 AI 也能正常运行：
- 气泡关键词路由（意图识别的本地版）
- 绩效打分本地规则（工资核算兜底）
- 岗位知识本地模板（进阶考核兜底）
- 考核出题本地模板（Dify 试题生成工作流兜底）
"""
import re
import random

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
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*", text)
    for n in nums:
        score += min(float(n) / 20, 5)
    score = max(50.0, min(95.0, score))
    return {
        "performance_score": round(score, 1),
        "reasoning": "(local rule)",
    }


# ============================================================
# 岗位知识本地模板（进阶考核兜底）
# ============================================================
_KNOWLEDGE_TEMPLATES = {
    "default": {
        "skills": ["业务熟练度", "沟通协调", "流程规范", "数据意识"],
        "management_abilities": ["团队协作", "任务拆解", "异常反馈"],
        "suggested_path": [
            "先在本岗位连续 2 个考核周期达标",
            "再申请参与跨部门项目",
            "最后竞聘目标岗位",
        ],
    }
}


def wf4_fallback(position: str) -> dict:
    t = _KNOWLEDGE_TEMPLATES["default"]
    return {
        "intro": (
            f"{position} is a key position in the company."
        ),
        "skills": t["skills"],
        "management_abilities": t["management_abilities"],
        "suggested_path": t["suggested_path"],
    }


# ============================================================
# 考核出题本地模板（Dify 试题生成工作流兜底）
# 单选3道x8分 + 多选4道x13分 + 判断3道x8分 = 100分
# ============================================================
_QUIZ_BANK = {
    "single": [
        {
            "q": "下列哪一项属于{pos}的主要工作职责？",
            "opts": ["跟进高层决议事项闭环", "负责大客户商务合同审核", "管理客服团队排班", "负责车队车辆维保管理"],
            "ans": 0,
        },
        {
            "q": "{pos}在跨部门协作中，最优先保障的是？",
            "opts": ["本部门KPI完成", "客户需求及时响应", "流程合规性", "成本控制"],
            "ans": 1,
        },
        {
            "q": "关于{pos}的岗位定位，以下描述最准确的是？",
            "opts": ["纯执行层岗位", "执行与管理兼顾的关键节点", "战略决策层", "独立闭环运作"],
            "ans": 1,
        },
        {
            "q": "{pos}在处理异常情况时，首先应该？",
            "opts": ["立即上报等待指示", "按预案先行处置再汇报", "通知相关方后继续原工作", "记录备案暂不处理"],
            "ans": 1,
        },
        {
            "q": "{pos}的核心胜任能力中，最重要的是？",
            "opts": ["技术操作能力", "沟通协调能力", "外语水平", "学历背景"],
            "ans": 1,
        },
        {
            "q": "以下哪项不属于{pos}的能力培养路径？",
            "opts": ["本岗位连续考核周期达标", "参与跨部门项目历练", "竞聘目标岗位", "脱离一线转全职培训"],
            "ans": 3,
        },
        {
            "q": "{pos}在数据报表工作中，应重点关注？",
            "opts": ["报表美观度", "数据准确性与时效性", "报表页数", "使用高级图表"],
            "ans": 1,
        },
        {
            "q": "关于{pos}的权限范围，正确的是？",
            "opts": ["可自主审批所有费用", "在授权额度内审批", "需所有事项报批", "无审批权限"],
            "ans": 1,
        },
    ],
    "multi": [
        {
            "q": "{pos}的胜任能力通常包含哪些？（多选）",
            "opts": ["业务熟练度", "沟通协调能力", "数据分析意识", "车辆故障维修能力"],
            "ans": [0, 1, 2],
        },
        {
            "q": "{pos}在日常工作中需要对接哪些部门？（多选）",
            "opts": ["财务部", "人力资源部", "客服团队", "车队/调度"],
            "ans": [0, 1, 2, 3],
        },
        {
            "q": "以下属于{pos}关键绩效指标的有？（多选）",
            "opts": ["任务按时完成率", "客户满意度", "异常处理时效", "考勤打卡率"],
            "ans": [0, 1, 2],
        },
        {
            "q": "{pos}提升专业能力的有效途径包括？（多选）",
            "opts": ["参加内部培训", "轮岗学习", "行业交流", "仅靠自学"],
            "ans": [0, 1, 2],
        },
        {
            "q": "关于{pos}的工作内容，正确的有？（多选）",
            "opts": ["执行既定流程", "反馈现场问题", "参与流程优化", "独立修改SOP"],
            "ans": [0, 1, 2],
        },
        {
            "q": "{pos}在团队协作中应做到？（多选）",
            "opts": ["信息同步共享", "主动补位支持", "各自为战效率优先", "冲突时升级协调"],
            "ans": [0, 1, 3],
        },
    ],
    "judge": [
        {"q": "{pos}可以在未经批准的情况下自行变更作业流程。", "ans": False},
        {"q": "{pos}遇到超出权限的事项应及时向上级或相关部门汇报。", "ans": True},
        {"q": "{pos}的考核结果仅与业绩指标挂钩，与行为规范无关。", "ans": False},
        {"q": "{pos}应主动参与公司组织的各类培训和考核。", "ans": True},
        {"q": "跨部门协作中，{pos}应以本部门利益为最高优先级。", "ans": False},
        {"q": "{pos}对工作中发现的问题和风险有义务及时上报。", "ans": True},
    ],
}


def wf5_fallback(position: str) -> dict:
    pos = position or "target_position"
    random.seed(hash(pos) % (2**32))
    singles = random.sample(_QUIZ_BANK["single"], min(3, len(_QUIZ_BANK["single"])))
    multis = random.sample(_QUIZ_BANK["multi"], min(4, len(_QUIZ_BANK["multi"])))
    judges = random.sample(_QUIZ_BANK["judge"], min(3, len(_QUIZ_BANK["judge"])))

    questions = []
    idx = 1
    for sq in singles:
        item = {
            "id": idx,
            "type": "single",
            "points": 8,
            "question": sq["q"].format(pos=pos),
            "options": list(sq["opts"]),
            "answer": sq["ans"],
        }
        questions.append(item)
        idx += 1

    for mq in multis:
        item = {
            "id": idx,
            "type": "multi",
            "points": 13,
            "question": mq["q"].format(pos=pos),
            "options": list(mq["opts"]),
            "answer": list(mq["ans"]),
        }
        questions.append(item)
        idx += 1

    for jq in judges:
        item = {
            "id": idx,
            "type": "judge",
            "points": 8,
            "question": jq["q"].format(pos=pos),
            "options": ["A. correct", "B. wrong"],
            "answer": 0 if jq["ans"] else 1,
        }
        questions.append(item)
        idx += 1

    return {
        "target_position": pos,
        "total_questions": len(questions),
        "max_score": 100,
        "questions": questions,
        "source": "local_fallback",
    }
