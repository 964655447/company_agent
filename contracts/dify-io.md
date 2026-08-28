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

## WF-7 员工考勤打卡（员工端）

用途：员工输入特定指令完成打卡，记录上传时间、判定是否迟到，并自动汇总周/月度考勤。

**职责边界（硬性）**

| 环节 | 谁做 | 原因 |
|------|------|------|
| 指令理解（上班卡/下班卡） | Dify | LLM 擅长自然语言 |
| 记录上传时间 | **后端** | LLM 无法获知服务端权威时间 |
| 迟到判定 | **后端** | 依赖规则常量 `WORK_START=09:00` |
| 周/月度统计聚合 | **后端** | 数字必须来自数据库，禁止 LLM 计算 |
| 结果播报话术 | Dify | 结构化数据 → 自然语言 |

**入参 inputs**
```json
{ "command": "打卡", "emp_id": "220406" }
```

**工作流内部调用**：`POST /api/attendance/wf-checkin`
```json
{ "emp_id": "220406", "action": "clock_in", "command": "打卡" }
```
> `action` ∈ `clock_in`（上班卡，默认）/ `clock_out`（下班卡）。
> 入参统一用字符串接收——Dify 变量未填写时会传空串，用 int 接收会直接 422。

**该接口返回**
```json
{
  "employee": { "emp_id": 220406, "name": "许梦", "department": "技术部", "position": "工程师" },
  "action": "clock_in",
  "checkin": {
    "success": true, "duplicated": false,
    "time": "2026-08-28 08:52:11", "type": "clock_in",
    "is_late": false, "late_minutes": 0,
    "work_start": "09:00",
    "message": "上班打卡成功（08:52），未迟到"
  },
  "week": {
    "period": "week", "range_start": "2026-08-24", "range_end": "2026-08-28",
    "workdays": 5, "days": 4, "absent_days": 1, "late_count": 1,
    "late_rate": "25%", "avg_clock_in": "08:52",
    "earliest": "08:40", "latest": "09:05", "record_count": 4
  },
  "month": {
    "period": "month", "range_start": "2026-08-01", "range_end": "2026-08-28",
    "workdays": 20, "days": 15, "absent_days": 5, "late_count": 2,
    "late_rate": "13%", "avg_clock_in": "08:48",
    "earliest": "08:30", "latest": "09:20", "record_count": 30
  }
}
```
> `duplicated=true` 表示当天已打过同类卡，本次未重复记录（原记录时间一并回传）。
> `absent_days = workdays - days`，`workdays` 为区间内周一~周五且已过去的天数。

**返回 outputs**
```json
{ "answer": "上班打卡成功，08:52 到岗，未迟到。本周已出勤 4 天，迟到 1 次……" }
```

**降级约定**：Dify 未配置或调用失败时，后端 `POST /api/attendance/command`
自行完成完全相同的打卡与统计，仅话术退化为模板拼接（返回 `ai=false`），功能不受影响。

---

## WF-8 管理端考勤分析

用途：按员工生成周/月度考勤数据，并分析员工行为、给出管理建议。

**入参 inputs**
```json
{ "period": "week", "dept": "", "manager_id": "220401" }
```
> `period` ∈ `week`（默认）/ `month` / `last_week` / `last_month`；
> `dept` 留空 = 全部部门；`manager_id` 用于数据权限隔离。

**工作流内部调用**：`POST /api/attendance/wf-team-report`
```json
{ "period": "week", "dept": "", "manager_id": "220401", "top_n": 50 }
```

**该接口返回**
```json
{
  "period": "week", "dept": "全部部门",
  "range_start": "2026-08-24", "range_end": "2026-08-28",
  "work_start": "09:00",
  "summary": {
    "headcount": 26, "total_days": 118, "total_late": 9,
    "avg_days": 4.5, "attendance_rate": "90.8%", "late_rate": "7.6%",
    "late_top":     [{ "name": "赵敏", "late_count": 3 }],
    "punctual_top": [{ "name": "许梦", "days": 5 }]
  },
  "employee_count": 26,
  "employees": [
    { "emp_id": 220407, "name": "赵敏", "department": "财务部", "position": "会计",
      "days": 4, "workdays": 5, "absent_days": 1, "late_count": 3,
      "late_rate": "75%", "avg_clock_in": "09:12",
      "earliest": "08:50", "latest": "09:35", "behavior": "偶有迟到" }
  ]
}
```
> `behavior` 为后端规则标签：`无考勤记录` / `全勤稳定` / `出勤良好` /
> `基本正常`（≤1 次迟到）/ `偶有迟到`（2~3 次）/ `迟到偏多`（>3 次）。
> `punctual_top` 只统计 `days > 0` 的员工，避免出勤 0 天的人进入表扬名单。

**返回 outputs**
```json
{ "analysis": "## 一、整体概况\n……\n## 二、需要关注的员工\n……" }
```
> 输出为 Markdown，固定四段结构：整体概况 / 需要关注的员工 / 表现突出的员工 / 管理建议。

**降级约定**：Dify 未配置时回退到 WF-5 的模板分析，管理端页面照常显示。

---

## 变更记录

| 日期 | 工作流 | 变更 | 提出人 |
|------|--------|------|--------|
| 2026-08-27 | 全部 | 初版定稿 | - |
| 2026-08-28 | WF-7 | 新增员工考勤打卡工作流（指令→打卡→判迟到→周月统计→播报） | - |
| 2026-08-28 | WF-8 | 新增管理端考勤分析工作流（按人聚合 + 员工行为分析） | - |
