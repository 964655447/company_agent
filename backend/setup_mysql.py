"""一次性初始化本地 MySQL：建库建表 + 灌花名册 + 生成 2026-08 示例考勤。

用法（在 backend 目录用 venv 执行）：
  python setup_mysql.py
"""
import json
import random
from datetime import date, datetime, timedelta

import bcrypt
import openpyxl
import pymysql

MYSQL = dict(host="127.0.0.1", port=3306, user="root", password="***REMOVED***")
DB_NAME = "company_agent"
ROSTER_XLSX = r"***REMOVED***"
SQL_PATH = r"***REMOVED***\contracts\database.sql"
WORK_START_HOUR, WORK_START_MIN = 9, 0  # 与 backend config.WORK_START 一致


def run_schema(conn):
    with conn.cursor() as cur:
        cur.execute(f"SHOW TABLES FROM {DB_NAME}")
        if cur.fetchone():
            print(f"[schema] 库 {DB_NAME} 已有表，跳过 DDL")
            return
    with open(SQL_PATH, encoding="utf-8") as f:
        sql = f.read()
    # 逐条执行（跳过纯注释/空行）
    stmts = []
    buf = ""
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf += line + "\n"
        if line.strip().endswith(";"):
            stmts.append(buf.strip())
            buf = ""
    with conn.cursor() as cur:
        for s in stmts:
            cur.execute(s)
    conn.commit()
    print(f"[schema] 已执行 {len(stmts)} 条 DDL（库 {DB_NAME} + 5 张表）")


def seed_employees(conn):
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
    # 2026-08 工作日（周一~周五），生成到今天 08-27
    end = date(2026, 8, 27)
    workdays = []
    d = date(2026, 8, 1)
    while d <= end:
        if d.weekday() < 5:  # 0=Mon ... 4=Fri
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
                # 上班：~12% 迟到
                late = random.random() < 0.12
                if late:
                    minute = random.randint(3, 42)
                else:
                    minute = random.randint(0, 55)
                cin = datetime(wd.year, wd.month, wd.day, WORK_START_HOUR, minute)
                cur.execute(ins, (eid, cin, "clock_in", late, wd))
                # 下班：18:00~18:45
                cout = datetime(wd.year, wd.month, wd.day, 18, random.randint(0, 45))
                cur.execute(ins, (eid, cout, "clock_out", False, wd))
                n += 2
        conn.commit()
        print(f"[attendance] 已生成 {n} 条记录（{len(emp_ids)} 人 × {len(workdays)} 工作日，含迟到样本）")


def main():
    conn = pymysql.connect(charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, **MYSQL)
    conn.select_db(DB_NAME)
    try:
        run_schema(conn)
        seed_employees(conn)
        gen_attendance(conn)
        # 统计预览
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) c FROM {DB_NAME}.employees")
            print("员工总数:", cur.fetchone()["c"])
            cur.execute(f"SELECT COUNT(*) c FROM {DB_NAME}.attendance")
            print("考勤总数:", cur.fetchone()["c"])
            cur.execute(f"SELECT COUNT(*) c FROM {DB_NAME}.attendance WHERE is_late=1")
            print("迟到总数:", cur.fetchone()["c"])
            cur.execute(f"SELECT COUNT(DISTINCT work_date) c FROM {DB_NAME}.attendance")
            print("覆盖工作日:", cur.fetchone()["c"])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
