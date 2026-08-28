"""验证后端在 MySQL 下的登录 + 考勤数据读取。"""
import requests

B = "http://127.0.0.1:8000"

# 1. 登录（许梦 220406）
r = requests.post(f"{B}/api/auth/login", json={"emp_id": 220406, "password": "EgRebcmQo4"})
print("登录:", r.status_code, r.json().get("name"), r.json().get("role"))
tok = r.json()["token"]
H = {"Authorization": f"Bearer {tok}"}

# 2. 本月考勤（MySQL 里的示例数据）
r = requests.get(f"{B}/api/attendance/my", params={"period": "month"}, headers=H)
d = r.json()
recs = d if isinstance(d, list) else d.get("records", d)
print("本月考勤接口:", r.status_code, "返回键:", list(d.keys()) if isinstance(d, dict) else f"list[{len(d)}]")
if isinstance(recs, list):
    print("记录数:", len(recs))
    if recs:
        print("首条:", recs[0])

# 3. 周报表（员工应 403）
r = requests.get(f"{B}/api/attendance/report", params={"period": "month"}, headers=H)
print("员工访问管理报表(应403):", r.status_code)

# 4. 管理者登录看月报表
r = requests.post(f"{B}/api/auth/login", json={"emp_id": 220401, "password": "GZVwRDW0a6b"})
tok2 = r.json()["token"]
r = requests.get(f"{B}/api/attendance/report", params={"period": "month"},
                 headers={"Authorization": f"Bearer {tok2}"})
print("管理者月报表:", r.status_code, str(r.json())[:300])
