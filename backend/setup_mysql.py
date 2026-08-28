"""一次性初始化本地 MySQL：建库建表（schema 来自 ../contracts/database.sql）。

同事 clone 仓库后的标准流程：
  1. cd backend
  2. cp ../.env.example .env        （按需填写 DB_URL；花名册路径可选）
  3. pip install -r requirements.txt
  4. python setup_mysql.py                     # 仅建库 + 5 张表
  5.（可选）python setup_mysql.py --seed-employees   # 需本机有花名册.xlsx
                                                  # 再设环境变量 SEED_ATTENDANCE=1 可生成演示考勤

注意：
  - 本文件只负责「结构」。员工/考勤等数据由各人自己的花名册.xlsx 灌入，不随仓库分发。
  - 若库里已存在任何表，run_schema 会跳过 DDL（防止覆盖你已有的数据）。
    要在本地启用新结构，请先 `DROP DATABASE company_agent;` 再重跑本脚本。
"""
import os
import re
import sys
from pathlib import Path

import pymysql

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
SQL_PATH = ROOT_DIR / "contracts" / "database.sql"


# ---------- 轻量读取 .env（不依赖 python-dotenv）----------
def load_dotenv() -> None:
    p = BASE_DIR / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_dotenv()


# ---------- 解析 DB_URL ----------
def parse_db_url(url: str) -> dict:
    # 兼容 mysql+pymysql:// 与 mysql:// 两种写法
    m = re.match(r"mysql\+?pymysql?://([^:]+):([^@]+)@([^:/]+):?(\d+)?/([^?]+)", url)
    if not m:
        raise SystemExit(
            f"[配置错误] 无法解析 DB_URL：{url}\n"
            f"示例：mysql+pymysql://root:密码@127.0.0.1:3306/company_agent"
        )
    user, pwd, host, port, db = m.groups()
    return dict(host=host, port=int(port or 3306), user=user, password=pwd, db=db)


DB_URL = os.environ.get(
    "DB_URL", "mysql+pymysql://root:***REMOVED***@127.0.0.1:3306/company_agent"
)
MYSQL = parse_db_url(DB_URL)
DB_NAME = MYSQL.pop("db")
ROSTER_XLSX = os.environ.get("ROSTER_XLSX", "")
SEED_ATTENDANCE = os.environ.get("SEED_ATTENDANCE", "") == "1"


def connect(**kw):
    return pymysql.connect(charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, **kw)


def run_schema(conn):
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        if cur.fetchall():
            print(f"[schema] 库 {DB_NAME} 已有表，跳过 DDL"
                  f"（如需重建请先 DROP DATABASE {DB_NAME} 再重跑）")
            return
    sql = SQL_PATH.read_text(encoding="utf-8")
    stmts, buf = [], ""
    for line in sql.splitlines():
        if line.strip().startswith("--"):   # 跳过注释行
            continue
        buf += line + "\n"
        if line.strip().endswith(";"):       # 以分号结尾才算一条完整语句
            stmts.append(buf.strip())
            buf = ""
    with conn.cursor() as cur:
        for s in stmts:
            cur.execute(s)
    conn.commit()
    print(f"[schema] 已执行 {len(stmts)} 条 DDL（库 {DB_NAME} + 5 张表）")


def seed_employees(conn):
    if not ROSTER_XLSX or not Path(ROSTER_XLSX).exists():
        print("[employees] 未设置 ROSTER_XLSX 或文件不存在，跳过导入"
              "（同事用各自花名册；管理者也可直接 INSERT employees 表）")
        return
    import json
    import bcrypt
    import openpyxl

    wb = openpyxl.load_workbook(ROSTER_XLSX)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    header, data = rows[0], rows[1:]
    print("[employees] 列头:", header)

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM {DB_NAME}.employees")
        if cur.fetchone()["c"] > 0:
            print("[employees] 已有数据，跳过导入（如需重导请先清空表）")
            return
        ins = (
            "INSERT INTO employees (no, emp_id, name, password_hash, permissions, position, department) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)"
        )
        for r in data:
            if not r or not r[1]:
                continue
            no_, name, emp_id, pwd, perms, position, dept = r[:7]
            permissions = [p.strip() for p in str(perms or "").split("、") if p.strip()]
            h = bcrypt.hashpw(str(pwd).encode(), bcrypt.gensalt()).decode()
            cur.execute(ins, (int(no_), int(emp_id), str(name).strip(), h,
                              json.dumps(permissions, ensure_ascii=False),
                              str(position).strip(), str(dept).strip()))
        conn.commit()
        print(f"[employees] 已导入 {len(data)} 名员工（bcrypt 哈希）")


def gen_attendance(conn):
    if not SEED_ATTENDANCE:
        print("[attendance] 未开启 SEED_ATTENDANCE，跳过（演示数据，同事一般不需）")
        return
    from datetime import date, datetime, timedelta
    import random

    end = date.today()
    workdays = []
    d = date(end.year, end.month, 1)
    while d <= end:
        if d.weekday() < 5:
            workdays.append(d)
        d += timedelta(days=1)

    with conn.cursor() as cur:
        cur.execute(f"SELECT id FROM {DB_NAME}.employees ORDER BY id")
        emp_ids = [row["id"] for row in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS c FROM {DB_NAME}.attendance")
        if cur.fetchone()["c"] > 0:
            print("[attendance] 已有数据，跳过生成")
            return
        ins = (
            "INSERT INTO attendance (employee_id, checkin_time, type, is_late, work_date) "
            "VALUES (%s,%s,%s,%s,%s)"
        )
        n = 0
        for eid in emp_ids:
            for wd in workdays:
                late = random.random() < 0.12
                minute = random.randint(3, 42) if late else random.randint(0, 55)
                cin = datetime(wd.year, wd.month, wd.day, 9, minute)
                cur.execute(ins, (eid, cin, "clock_in", late, wd))
                cout = datetime(wd.year, wd.month, wd.day, 18, random.randint(0, 45))
                cur.execute(ins, (eid, cout, "clock_out", False, wd))
                n += 2
        conn.commit()
        print(f"[attendance] 已生成 {n} 条记录（{len(emp_ids)} 人 × {len(workdays)} 工作日）")


def main():
    conn = connect(**MYSQL)
    conn.select_db(DB_NAME)
    try:
        run_schema(conn)
        if "--seed-employees" in sys.argv:
            seed_employees(conn)
        gen_attendance(conn)
        with conn.cursor() as cur:
            for t in ("employees", "attendance", "reimbursement", "salary", "assessment_log"):
                cur.execute(f"SELECT COUNT(*) c FROM {DB_NAME}.{t}")
                print(f"  表 {t}: {cur.fetchone()['c']} 行")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
