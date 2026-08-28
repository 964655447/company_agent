-- ============================================================
-- 公司管理智能体 · 演示数据（确定性 SQL，非随机生成）
-- 由启动器「生成演示数据」按钮 / `python backend/setup_mysql.py --seed-demo` 执行
-- 规则：
--   - 数据全部写在这里，可人工审查与修改；
--   - 每段都带幂等守卫：表已非空则跳过，可反复执行不重复造数；
--   - 员工用 INSERT IGNORE（库里已有则不重复插入）；
--   - 报销/考核日志通过姓名引用员工，姓名不存在时回退到首条员工，
--     因此既能在「全新库」跑，也能在你这种「已有员工」的库上补空表。
-- 注意：本文件假定表已建好（contracts/database.sql）。
--       清空重来请先 DROP DATABASE company_agent; 或在启动器勾选「重置演示数据」。
-- ============================================================

-- ------------------------------------------------------------
-- 1) employees 花名册（26 人，id 固定 1..26，默认密码 123456）
-- ------------------------------------------------------------
INSERT IGNORE INTO employees (id, no, emp_id, name, password_hash, permissions, position, department) VALUES
(1,  1, 220401, '冯霞', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办","商务部","技术部","人事部","财务部"]', '总经理',     '总经办'),
(2,  2, 220402, '许梦', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["商务部"]',           '商务专员',   '商务部'),
(3,  3, 220403, '张伟', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["技术部"]',           '技术经理',   '技术部'),
(4,  4, 220404, '王芳', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["人事部"]',           '人事经理',   '人事部'),
(5,  5, 220405, '李娜', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["财务部"]',           '财务经理',   '财务部'),
(6,  6, 220406, '刘洋', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办"]',           '总经理助理', '总经办'),
(7,  7, 220407, '陈静', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["商务部"]',           '商务经理',   '商务部'),
(8,  8, 220408, '杨磊', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["技术部"]',           '工程师',     '技术部'),
(9,  9, 220409, '赵敏', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["人事部"]',           '人事专员',   '人事部'),
(10, 10, 220410, '黄强', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["财务部"]',           '会计',       '财务部'),
(11, 11, 220411, '周婷', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办"]',           '总经理',     '总经办'),
(12, 12, 220412, '吴昊', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["商务部"]',           '商务专员',   '商务部'),
(13, 13, 220413, '徐丽', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["技术部"]',           '测试工程师', '技术部'),
(14, 14, 220414, '孙鹏', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["人事部"]',           '人事经理',   '人事部'),
(15, 15, 220415, '马超', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["财务部"]',           '财务经理',   '财务部'),
(16, 16, 220416, '朱琳', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办"]',           '总经理助理', '总经办'),
(17, 17, 220417, '胡军', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["商务部"]',           '商务经理',   '商务部'),
(18, 18, 220418, '郭涛', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["技术部"]',           '工程师',     '技术部'),
(19, 19, 220419, '林峰', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["人事部"]',           '人事专员',   '人事部'),
(20, 20, 220420, '何雪', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["财务部"]',           '会计',       '财务部'),
(21, 21, 220421, '高翔', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办"]',           '总经理',     '总经办'),
(22, 22, 220422, '罗薇', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["商务部"]',           '商务专员',   '商务部'),
(23, 23, 220423, '郑凯', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["技术部"]',           '技术经理',   '技术部'),
(24, 24, 220424, '梁爽', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["人事部"]',           '人事经理',   '人事部'),
(25, 25, 220425, '宋佳', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["财务部"]',           '财务经理',   '财务部'),
(26, 26, 220426, '唐勇', '$2b$12$2OKI1c1OHnFcGZ36hm.IKu/kGpcctYtBDAeZctsut1kVAAAYfC7OG', '["总经办"]',           '总经理助理', '总经办');

-- ------------------------------------------------------------
-- 2) attendance 考勤（本月工作日；员工已存在则跳过，避免重复）
-- ------------------------------------------------------------
INSERT INTO attendance (employee_id, checkin_time, type, is_late, work_date)
WITH RECURSIVE nums(n) AS (
  SELECT 0 UNION ALL SELECT n+1 FROM nums WHERE n < 31
),
month_days(d) AS (
  SELECT DATE_ADD(DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE())-1 DAY), INTERVAL n DAY)
  FROM nums WHERE n < DAYOFMONTH(CURDATE())
)
SELECT e.id,
       TIMESTAMP(md.d, MAKETIME(9, (e.id + DAY(md.d)) % 12, 0)),
       'clock_in',
       (e.id + DAY(md.d)) % 12 > 9,
       md.d
FROM month_days md JOIN employees e
WHERE DAYOFWEEK(md.d) BETWEEN 2 AND 6
  AND (SELECT COUNT(*) FROM attendance) = 0;

INSERT INTO attendance (employee_id, checkin_time, type, is_late, work_date)
WITH RECURSIVE nums(n) AS (
  SELECT 0 UNION ALL SELECT n+1 FROM nums WHERE n < 31
),
month_days(d) AS (
  SELECT DATE_ADD(DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE())-1 DAY), INTERVAL n DAY)
  FROM nums WHERE n < DAYOFMONTH(CURDATE())
)
SELECT e.id,
       TIMESTAMP(md.d, MAKETIME(18, (e.id + DAY(md.d) + 5) % 30, 0)),
       'clock_out',
       0,
       md.d
FROM month_days md JOIN employees e
WHERE DAYOFWEEK(md.d) BETWEEN 2 AND 6
  AND (SELECT COUNT(*) FROM attendance) = 0;

-- ------------------------------------------------------------
-- 3) salary 工资核算（按岗位算基本工资/绩效/津贴；字段严格 9 列）
--    gross_salary = base_salary + performance_bonus + allowance
-- ------------------------------------------------------------
INSERT INTO salary (no, id, name, position, base_salary, performance_rating, performance_bonus, allowance, gross_salary)
SELECT no, emp_id, name, position, base, rating,
       ROUND(base * CASE rating WHEN 'S' THEN 0.40 WHEN 'A' THEN 0.30 WHEN 'B' THEN 0.20 WHEN 'C' THEN 0.10 ELSE 0.0 END, 2) AS performance_bonus,
       allow,
       ROUND(base + base * CASE rating WHEN 'S' THEN 0.40 WHEN 'A' THEN 0.30 WHEN 'B' THEN 0.20 WHEN 'C' THEN 0.10 ELSE 0.0 END + allow, 2) AS gross_salary
FROM (
  SELECT e.no, e.emp_id, e.name, e.position,
         CASE e.position
           WHEN '总经理' THEN 25000 WHEN '总经理助理' THEN 12000
           WHEN '商务经理' THEN 16000 WHEN '商务专员' THEN 9000
           WHEN '技术经理' THEN 18000 WHEN '工程师' THEN 14000 WHEN '测试工程师' THEN 13000
           WHEN '人事经理' THEN 15000 WHEN '人事专员' THEN 8500
           WHEN '财务经理' THEN 16000 WHEN '会计' THEN 9500
           ELSE 9000 END AS base,
         CASE e.position
           WHEN '总经理' THEN 'S' WHEN '总经理助理' THEN 'A'
           WHEN '商务经理' THEN 'A' WHEN '技术经理' THEN 'A'
           WHEN '人事经理' THEN 'A' WHEN '财务经理' THEN 'A'
           ELSE 'B' END AS rating,
         CASE e.department
           WHEN '总经办' THEN 1500 WHEN '商务部' THEN 800 WHEN '技术部' THEN 1000
           WHEN '人事部' THEN 700 WHEN '财务部' THEN 800 ELSE 800 END AS allow
  FROM employees e
) t
WHERE (SELECT COUNT(*) FROM salary) = 0;

-- ------------------------------------------------------------
-- 4) reimbursement 费用报销（姓名引用，缺失回退首条员工；已存在则跳过）
-- ------------------------------------------------------------
INSERT INTO reimbursement (employee_id, category, amount, status, approver_id, submit_time)
SELECT * FROM (
  SELECT COALESCE((SELECT id FROM employees WHERE name='冯霞'), (SELECT id FROM employees ORDER BY id LIMIT 1)) AS employee_id,
         '差旅费' AS category, 2500.00 AS amount, 'approved' AS status,
         COALESCE((SELECT id FROM employees WHERE name='冯霞'), (SELECT id FROM employees ORDER BY id LIMIT 1)) AS approver_id,
         DATE_SUB(NOW(), INTERVAL 5 DAY) AS submit_time
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='许梦'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '交通费', 320.00, 'submitted', NULL, DATE_SUB(NOW(), INTERVAL 3 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='张伟'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '餐饮费', 680.50, 'approving', NULL, DATE_SUB(NOW(), INTERVAL 8 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='李娜'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '办公用品', 450.00, 'approved',
         COALESCE((SELECT id FROM employees WHERE name='冯霞'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         DATE_SUB(NOW(), INTERVAL 12 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='王芳'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '培训费', 1800.00, 'rejected',
         COALESCE((SELECT id FROM employees WHERE name='冯霞'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         DATE_SUB(NOW(), INTERVAL 20 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='刘洋'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '差旅费', 3200.00, 'approved',
         COALESCE((SELECT id FROM employees WHERE name='许梦'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         DATE_SUB(NOW(), INTERVAL 15 DAY)
) t
WHERE (SELECT COUNT(*) FROM reimbursement) = 0;

-- ------------------------------------------------------------
-- 5) assessment_log 考核查询日志（姓名引用，缺失回退首条员工；已存在则跳过）
-- ------------------------------------------------------------
INSERT INTO assessment_log (employee_id, position_queried, queried_at)
SELECT * FROM (
  SELECT COALESCE((SELECT id FROM employees WHERE name='许梦'), (SELECT id FROM employees ORDER BY id LIMIT 1)) AS employee_id,
         '工程师' AS position_queried, DATE_SUB(NOW(), INTERVAL 2 DAY) AS queried_at
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='张伟'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '商务经理', DATE_SUB(NOW(), INTERVAL 6 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='陈静'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '会计', DATE_SUB(NOW(), INTERVAL 9 DAY)
  UNION ALL
  SELECT COALESCE((SELECT id FROM employees WHERE name='杨磊'), (SELECT id FROM employees ORDER BY id LIMIT 1)),
         '技术经理', DATE_SUB(NOW(), INTERVAL 14 DAY)
) t
WHERE (SELECT COUNT(*) FROM assessment_log) = 0;
