"""全流程接口测试：登录/打卡/报销/工资/考核/聊天/管理报告/花名册。"""
import json
import httpx

B = "http://127.0.0.1:8000"
c = httpx.Client(base_url=B, timeout=30)
PASS = {"220401": "GZVwRDW0a6b", "220406": "EgRebcmQo4"}


def login(emp_id, pwd):
    r = c.post("/api/auth/login", json={"emp_id": emp_id, "password": pwd})
    assert r.status_code == 200, r.text
    d = r.json()
    c.headers["Authorization"] = f"Bearer {d['token']}"
    return d


def show(title, r):
    body = r.json() if r.status_code != 204 else None
    text = json.dumps(body, ensure_ascii=False)
    print(f"[{r.status_code}] {title}: {text[:260]}{'...' if len(text) > 260 else ''}")
    return body


# ---- 管理者 冯霞 ----
mgr = login(220401, PASS["220401"])
print(f"登录 OK: {mgr['name']} role={mgr['role']} perms={mgr['permissions']}")

show("打卡", c.post("/api/attendance/checkin", json={"type": "clock_in"}))
show("我的考勤", c.get("/api/attendance/my", params={"period": "week"}))

show("提交报销(缺项)", c.post("/api/reimbursement/submit",
     data={"category": "", "amount": "0", "desc": ""}))
show("提交报销(完整)", c.post("/api/reimbursement/submit",
     data={"category": "交通", "amount": "356.5", "desc": "出差高铁票"}))

show("绩效→工资条", c.post("/api/salary/submit-performance",
     json={"achievements": "本月完成3个大单，回款率95%，客户零投诉"}))
show("我的工资条", c.get("/api/salary/my"))

show("岗位查询", c.post("/api/assessment/query", json={"position": "调度经理"}))
show("聊天-考勤", c.post("/api/chat", json={"message": "我这个月迟到几次了"}))
show("聊天-工资", c.post("/api/chat", json={"message": "我的最新工资条"}))
show("AI状态", c.get("/api/chat/status"))

show("考勤报告", c.get("/api/attendance/report", params={"period": "week"}))
show("报销报告", c.get("/api/reimbursement/report"))
show("工资报告", c.get("/api/salary/report"))
show("考核统计", c.get("/api/assessment/stats"))
roster = show("花名册", c.get("/api/roster"))

# 审批第一张待审单
rep = c.get("/api/reimbursement/report").json()
pending = [r for r in rep["rows"] if r["status"] in ("submitted", "approving")]
if pending:
    show("审批报销", c.post(f"/api/reimbursement/{pending[0]['id']}/review",
         json={"action": "approve"}))

# ---- 员工 许梦：权限隔离验证 ----
emp = login(220406, PASS["220406"])
print(f"\n员工登录 OK: {emp['name']} role={emp['role']}")
show("员工访问花名册(应403)", c.get("/api/roster"))
show("员工访问工资报告(应403)", c.get("/api/salary/report"))
show("员工打卡", c.post("/api/attendance/checkin", json={"type": "clock_in"}))

print("\n全部接口测试完成 ✓")
