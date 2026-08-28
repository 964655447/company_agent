"""一次性初始化本地 MySQL：建库建表（schema 来自 ../contracts/database.sql）。

同事 clone 仓库后的标准流程（也可由启动器 launcher 自动调用，无需手动跑）：
  1. cd backend
  2. cp ../.env.example .env        （或首次启动启动器时网页填写数据库信息）
  3. pip install -r requirements.txt
  4. python setup_mysql.py                     # 自动建库 + 5 张表（幂等，可重复跑）
  5.（可选）python setup_mysql.py --seed-demo         # 执行 contracts/seed.sql 灌入演示数据（幂等，已非空表跳过）
                                                  # 加 --reset 则先清空 5 张表再重灌
  6.（可选）python setup_mysql.py --seed-employees   # 需本机有花名册.xlsx
                                                  # 再设环境变量 SEED_ATTENDANCE=1 可生成演示考勤

注意：
  - 本文件只负责「结构」。员工/考勤等数据由各人自己的花名册.xlsx 灌入，不随仓库分发。
  - ensure_database() 会 CREATE DATABASE IF NOT EXISTS 并建表；表已存在则跳过 DDL（不覆盖数据）。
    要在本地启用新结构（如工资表 v2），请执行 contracts/migrate_salary_v2.sql。
"""
import os
import re
import sys
from pathlib import Path

import pymysql
import random
import json
from datetime import date, datetime, timedelta

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


def ensure_database(conn=None):
    """确保数据库与表存在（幂等）。返回结果 dict。

    - 库不存在则 CREATE DATABASE IF NOT EXISTS；
    - 已存在则跳过建库；
    - 进入库后调用 run_schema 建表（已有表跳过 DDL）。
    可被启动器 subprocess 调用，也可直接 import 使用。
    """
    own = conn is None
    if own:
        conn = connect(**{k: v for k, v in MYSQL.items()})
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
        conn.select_db(DB_NAME)
        run_schema(conn)
        return {"ok": True, "msg": f"数据库 {DB_NAME} 已就绪（建库/建表完成）"}
    except Exception as e:
        return {"ok": False, "msg": f"数据库初始化失败: {e}"}
    finally:
        if own:
            conn.close()


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



# ------------------------------------------------------------
# 演示数据：从 contracts/seed.sql 读取确定性 SQL 并执行（非随机生成器）
# 用法：
#   python setup_mysql.py --seed-demo            # 仅对空表造数（seed.sql 各段自带幂等守卫）
#   python setup_mysql.py --seed-demo --reset    # 清空 5 张表后重新造数
# 说明：数据全部写在 contracts/seed.sql（可被人工审查/修改），本函数只负责执行。
# ------------------------------------------------------------
SEED_SQL_PATH = ROOT_DIR / "contracts" / "seed.sql"


def seed_from_sql(conn):
    if not SEED_SQL_PATH.exists():
        print(f"[seed] 未找到 {SEED_SQL_PATH}，跳过（如需演示数据请确认 contracts/seed.sql 存在）")
        return
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")
    stmts, buf = [], ""
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf += line + "\n"
        if line.strip().endswith(";"):
            stmts.append(buf.strip())
            buf = ""
    with conn.cursor() as cur:
        n = 0
        for s in stmts:
            cur.execute(s)
            conn.commit()   # 每条提交一次：单条失败不影响前面已写入的数据
            n += 1
    print(f"[seed] 已执行 {n} 条演示数据 SQL（来自 contracts/seed.sql）")


def _reset_all(conn):
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in ("assessment_log", "reimbursement", "attendance", "salary", "employees"):
            cur.execute(f"DELETE FROM {DB_NAME}.{t}")
            cur.execute(f"ALTER TABLE {DB_NAME}.{t} AUTO_INCREMENT=1")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    print("[reset] 已清空 5 张表")


def seed_demo(conn, reset=False):
    if reset:
        _reset_all(conn)
    seed_from_sql(conn)
    print("[seed-demo] 演示数据生成完成")


def main():
    conn = connect(**{k: v for k, v in MYSQL.items()})
    try:
        ensure_database(conn)
        if "--seed-demo" in sys.argv:
            seed_demo(conn, reset="--reset" in sys.argv)
        elif "--seed-employees" in sys.argv:
            seed_employees(conn)
            if SEED_ATTENDANCE:
                gen_attendance(conn)
        elif SEED_ATTENDANCE:
            gen_attendance(conn)
        with conn.cursor() as cur:
            for t in ("employees", "attendance", "reimbursement", "salary", "assessment_log"):
                cur.execute(f"SELECT COUNT(*) c FROM {DB_NAME}.{t}")
                print(f"  表 {t}: {cur.fetchone()['c']} 行")
    finally:
        conn.close()
