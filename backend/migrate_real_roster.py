"""一次性把 employees 改成真实 26 人花名册（密码统一 123456），
   并级联删除多余的 220427（attendance + employee_salary + employees）。

   使用方式：直接 python 跑（在 backend/ 目录下）。
   幂等性：重跑会再次覆盖 26 行 + 再次尝试删 220427（DELETE 无副作用）。
"""
import json
import sys
import pymysql
import bcrypt

DB_KW = dict(host="127.0.0.1", port=3306, user="root",
             password="964655", database="company_agent", charset="utf8mb4")

# 真实花名册（严格按用户给定的 26 行）
ROSTER = [
    # no, name, employee_id, permissions_str, position, department
    # 注：密码统一 123456（bcrypt），不存用户真实登录密码。
    (1,  "冯霞",   220401, "总经办、商务部、运营部、车队、财务部",                     "总经理",      "总经办"),
    (2,  "胡倩",   220402, "总经办、商务部、运营部、车队、财务部",                     "总经理助理",  "总经办"),
    (3,  "黄秀英", 220403, "商务总监、营销经理、营销专员",                              "商务总监",    "商务部"),
    (4,  "赵秀兰", 220404, "营销经理、营销专员",                                        "营销经理",    "商务部"),
    (5,  "谢洋",   220405, "营销经理、营销专员",                                        "营销经理",    "商务部"),
    (6,  "许梦",   220406, "营销专员",                                                  "营销专员",    "商务部"),
    (7,  "李思",   220407, "营销专员",                                                  "营销专员",    "商务部"),
    (8,  "郑磊",   220408, "运营总监、调度经理、调度专员",                              "运营总监",    "运营部"),
    (9,  "许磊",   220409, "调度经理、调度专员",                                        "调度经理",    "运营部"),
    (10, "高秀兰", 220410, "调度专员",                                                  "调度专员",    "运营部"),
    (11, "李洋",   220411, "调度专员",                                                  "调度专员",    "运营部"),
    (12, "何玲",   220412, "运营经理、运营专员",                                        "运营经理",    "运营部"),
    (13, "胡娟",   220413, "运营专员",                                                  "运营专员",    "运营部"),
    (14, "袁芬",   220414, "运营专员",                                                  "运营专员",    "运营部"),
    (15, "杨思",   220415, "客服经理、客服专员",                                        "客服经理",    "运营部"),
    (16, "董秀英", 220416, "客服专员",                                                  "客服专员",    "运营部"),
    (17, "傅秀英", 220417, "客服专员",                                                  "客服专员",    "运营部"),
    (18, "杨梦",   220418, "总车队长、车队长、车队文员",                                "总车队长",    "车队"),
    (19, "梁怡",   220419, "车队长、车队文员",                                          "车队长",      "车队"),
    (20, "林飞",   220420, "车队长、车队文员",                                          "车队长",      "车队"),
    (21, "萧平",   220421, "车队文员",                                                  "车队文员",    "车队"),
    (22, "陈平",   220422, "车队文员",                                                  "车队文员",    "车队"),
    (23, "邓玲",   220423, "财务总监、会计、出纳、审核",                                "财务总监",    "财务部"),
    (24, "罗强",   220424, "会计",                                                      "会计",        "财务部"),
    (25, "林伟",   220425, "出纳",                                                      "出纳",        "财务部"),
    (26, "冯华",   220426, "审核",                                                      "审核",        "财务部"),
]

DROP_EID = 220427  # 多出的演示行


def perms_to_json(s: str):
    return json.dumps([x.strip() for x in s.split("、") if x.strip()], ensure_ascii=False)


def main():
    conn = pymysql.connect(**DB_KW)
    cur = conn.cursor()

    # 0) 备份现状
    cur.execute("SELECT COUNT(*) FROM employees")
    emp_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM attendance WHERE employee_id=%s", (DROP_EID,))
    att_drop = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM employee_salary WHERE employee_id=%s", (DROP_EID,))
    sal_drop = cur.fetchone()[0]
    print(f"[before] employees={emp_before}  attendance(220427)={att_drop}  employee_salary(220427)={sal_drop}")

    # 1) 生成 123456 的 bcrypt hash
    pw_hash = bcrypt.hashpw("123456".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print(f"[hash] 123456 -> {pw_hash[:25]}... ({len(pw_hash)} chars)")

    try:
        conn.begin()

        # 2) UPDATE 26 行
        upd_sql = ("UPDATE employees SET name=%s, employee_id=%s, password_hash=%s, "
                   "permissions=%s, position=%s, department=%s WHERE no=%s")
        upd_n = 0
        for no, name, eid, perms_s, pos, dept in ROSTER:
            cur.execute(upd_sql, (name, eid, pw_hash, perms_to_json(perms_s), pos, dept, no))
            upd_n += cur.rowcount
        print(f"[update] {upd_n} 行 employees 已更新（预期 26）")

        # 3) 删除 220427 关联（先子表后父表，避开外键）
        cur.execute("DELETE FROM attendance WHERE employee_id=%s", (DROP_EID,))
        att_del = cur.rowcount
        cur.execute("DELETE FROM employee_salary WHERE employee_id=%s", (DROP_EID,))
        sal_del = cur.rowcount
        cur.execute("DELETE FROM employees WHERE employee_id=%s", (DROP_EID,))
        emp_del = cur.rowcount
        print(f"[delete] attendance={att_del}  employee_salary={sal_del}  employees={emp_del}  (220427 全部清理)")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] rolled back: {e}")
        sys.exit(1)

    # 4) 验证
    cur.execute("SELECT COUNT(*) FROM employees")
    emp_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM employees WHERE employee_id=%s", (DROP_EID,))
    leftover = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM attendance WHERE employee_id=%s", (DROP_EID,))
    att_left = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM employee_salary WHERE employee_id=%s", (DROP_EID,))
    sal_left = cur.fetchone()[0]
    print(f"[after]  employees={emp_after} (期望 26)  220427 残留: emp={leftover} att={att_left} sal={sal_left}")

    if emp_after != 26 or leftover or att_left or sal_left:
        print("[WARN] 验证未通过，请人工核查")
    else:
        print("[OK] 迁移完成，结构干净")

    # 5) 抽样 3 行打印，确认姓名/岗位/部门写入正确
    cur.execute("""SELECT no, employee_id, name, position, department, permissions
                   FROM employees WHERE no IN (1,2,3,26) ORDER BY no""")
    for r in cur.fetchall():
        print("  sample:", r)
    conn.close()


if __name__ == "__main__":
    main()
