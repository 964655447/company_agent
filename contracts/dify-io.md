# Dify 工作流 · 输入/输出契约 v0.1

> 用途：**Dify 团队 ↔ 前后端** 的对接契约。后端按「入参」构造请求，按「返回」解析落库。
> 硬性规则：所有工作流的直接回复必须是**合法 JSON**（不允许纯自然语言段落），字段名用英文 snake_case。
> 任何字段变更：先改本文件 → 群里同步 → 再改工作流。

---

## 通用调用方式

后端统一走 Dify 的 `POST /v1/workflows/run`（阻塞模式）：

```
POST {DIFY_BASE_URL}/v1/workflows/run
Authorization: Bearer {API_KEY}          # 每个工作流一个独立 Key
Content-Type: application/json

{
  "inputs": { ...本工作流入参... },
  "response_mode": "blocking",
  "user": "emp-{employee_id}"           # 员工标识，用于 Dify 侧日志
}
```

返回解析：取 `data.outputs` 里的约定字段。

---

## WF-1 身份意图识别（共有部分）

用途：把员工的一句话路由到具体模块（打卡/报销/工资/考核/闲聊）。

**入参 inputs**
```json
{ "user_message": "我今天迟到了吗" }
```

**返回 outputs**
```json
{
  "module": "attendance",        // attendance|reimbursement|salary|assessment|chat
  "action": "query_my",          // 模块内细分动作，后端按此分发
  "params": { "period": "month" }
}
```

> 后端拿到 module/action 后自己调对应接口，**不**由 Dify 直接返回业务数据。

---

## WF-2 报销材料 OCR 抽取

用途：发票/票据图片 → 结构化字段 + 缺项判断。

**入参 inputs**
```json
{ "image_url": "https://..." }   // 后端先上传图片拿到可访问 URL 再传入
```

**返回 outputs**
```json
{
  "category": "交通",             // 类目；识别不了则 ""
  "amount": 128.5,              // 数字；识别不了则 null
  "date": "2026-08-20",          // null 表示缺失
  "vendor": "xx出租车",
  "missing": ["amount", "date"]  // 缺失字段名列表，无缺失则 []
}
```

---

## WF-3 绩效抽取与工资计算

用途：绩效达成描述 → 结构化绩效 → 工资条金额。

**入参 inputs**
```json
{
  "emp_id": 220406,
  "employee_name": "许梦",
  "position": "营销专员",
  "department": "商务部",
  "achievements": "本月完成3个大单，回款率95%"   // 员工原始输入
}
```

**返回 outputs**
```json
{
  "performance_score": 88.5,      // 0-100
  "performance_wage": 4200.00,    // 绩效工资
  "reasoning": "完成度高于目标…"   // 计算依据说明（展示给员工）
}
```

> 基本工资/补贴由后端从数据库基数表读取，不经过 Dify。

---

## WF-4 岗位知识 RAG（进阶考核）

用途：输入岗位 → 返回该岗位介绍与能力要求。

**入参 inputs**
```json
{ "position": "调度经理", "employee_name": "李洋" }
```

**返回 outputs**
```json
{
  "intro": "调度经理负责……",
  "skills": ["排班统筹", "异常调度", "沟通协调"],
  "management_abilities": ["团队管理", "压力决策"],
  "suggested_path": ["先兼任……", "再……"]
}
```

---

## WF-5 分析报告生成（管理端共用）

用途：后端先算好统计数据，Dify 只负责「写分析文案」。

**入参 inputs**
```json
{
  "report_type": "attendance",     // attendance|reimbursement|salary
  "period": "2026-08",
  "stats_json": "{\"late_count\":12,\"late_top\":[{\"name\":\"李洋\",\"count\":5}]}"
}
```

**返回 outputs**
```json
{
  "analysis": "本月迟到12人次，李洋迟到5次居首，建议……"
}
```

> **关键原则：数字永远由后端统计后传入，Dify 不自己编数字**，只负责解读。

---

## WF-7 员工考勤打卡（已撤销）

> 该工作流于 2026-08-28 撤销，Dify 侧 DSL 已删除。打卡与周/月统计改为后端纯本地实现
> （见 `backend/app/routers/attendance.py` 的 `/command` 接口），不再依赖外部 AI。

## WF-8 管理端考勤分析（已撤销）

> 该工作流于 2026-08-28 撤销，Dify 侧 DSL 已删除。管理端考勤分析改为后端纯本地实现
> （见 `backend/app/routers/attendance.py` 的 `/report` 接口，复用 WF-5 模板分析），不再依赖外部 AI。

---

## 变更记录

| 日期 | 工作流 | 变更 | 提出人 |
|------|--------|------|--------|
| 2026-08-27 | 全部 | 初版定稿 | - |
| 2026-08-28 | WF-7 / WF-8 | 撤销两个考勤工作流（Dify 侧 DSL 删除，接口改为纯本地实现） | - |
