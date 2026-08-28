-- ============================================================
-- 工资核算表结构迁移 v1 → v2
-- 适用：本地/同事库里已存在旧 salary 表（employee_id/period/base/...
--       等老字段），需要换成新扁平结构（NO/工号/姓名/岗位/基本工资/
--       绩效评级/绩效奖金/津贴/应发工资）。
-- 安全性：salary 为可重算的派生表，本脚本 DROP 后重建；
--         employees / attendance / reimbursement / assessment_log 不受影响。
-- 执行（在 backend 目录、已配好 DB_URL 的 venv 下）：
--   python -c "import pymysql,os; from setup_mysql import MYSQL,DB_NAME; \
--     c=pymysql.connect(charset='utf8mb4',**MYSQL); \
--     c.cursor().execute(open(r'../contracts/migrate_salary_v2.sql',encoding='utf-8').read()); \
--     c.commit(); print('salary 表已迁移为 v2')"
-- 或直接用 mysql 客户端：
--   mysql -uroot -p company_agent < contracts/migrate_salary_v2.sql
-- ============================================================

DROP TABLE IF EXISTS salary;

CREATE TABLE salary (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  no                 INT           NOT NULL            COMMENT '花名册序号 → employees.no',
  emp_id             BIGINT        NOT NULL            COMMENT '工号（登录账号） → employees.emp_id',
  name               VARCHAR(32)   NOT NULL            COMMENT '姓名',
  position           VARCHAR(64)   NOT NULL            COMMENT '岗位',
  base_salary        DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '基本工资',
  performance_rating VARCHAR(8)    NOT NULL DEFAULT 'C' COMMENT '绩效评级 S/A/B/C/D',
  performance_bonus  DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '绩效奖金',
  allowance          DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '津贴/补贴',
  gross_salary       DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '应发工资 = 基本+绩效奖金+津贴',
  period             VARCHAR(7)    NOT NULL DEFAULT '' COMMENT '所属月 YYYY-MM（留空表示最新核算）',
  created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_sal_emp_period (emp_id, period)
) COMMENT='工资核算表';
