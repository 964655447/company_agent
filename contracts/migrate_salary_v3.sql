-- ============================================================
-- 工资核算表 v2（12 列：含 id 自增主键 / emp_id / period / created_at）
--   → v3（严格 9 列：no, id, name, position, base_salary,
--          performance_rating, performance_bonus, allowance, gross_salary）
-- 说明：
--   - 新结构以「工号(id)」为主键，每位员工一条工资核算记录；
--   - 本迁移保留每位员工最新一期（按 created_at）的数据，其余丢弃；
--   - 若 salary 表已是 9 列结构（全新库），直接跳过本脚本即可。
-- 用法（在已建库的前提下执行）：
--   python backend/setup_mysql.py  会自动建 9 列表（全新库）；
--   已有旧 12 列表则需先跑本迁移：
--   mysql -u<用户> -p company_agent < contracts/migrate_salary_v3.sql
--   或启动器「生成演示数据」前，本地先执行此迁移。
-- ============================================================

-- 仅在存在旧列 emp_id 时才执行（全新 9 列表不处理）
SET @has_old = (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'salary' AND column_name = 'emp_id'
);

DROP PROCEDURE IF EXISTS _mig_salary_v3;
DELIMITER //
CREATE PROCEDURE _mig_salary_v3()
BEGIN
  IF @has_old > 0 THEN
    CREATE TABLE salary_new (
      no                 INT           NOT NULL            COMMENT '序号（花名册序号）',
      id                 BIGINT        NOT NULL PRIMARY KEY COMMENT '工号（ID，登录账号）',
      name               VARCHAR(32)   NOT NULL            COMMENT '姓名',
      position           VARCHAR(64)   NOT NULL            COMMENT '岗位',
      base_salary        DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '基本工资',
      performance_rating VARCHAR(8)    NOT NULL DEFAULT 'C' COMMENT '绩效评级 S/A/B/C/D',
      performance_bonus  DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '绩效奖金',
      allowance          DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '津贴/补贴',
      gross_salary       DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '应发工资 = 基本+绩效奖金+津贴'
    ) COMMENT='工资核算表';

    INSERT INTO salary_new (no, id, name, position, base_salary, performance_rating, performance_bonus, allowance, gross_salary)
    SELECT no, emp_id, name, position, base_salary, performance_rating, performance_bonus, allowance, gross_salary
    FROM salary s
    WHERE NOT EXISTS (
      SELECT 1 FROM salary s2
      WHERE s2.emp_id = s.emp_id AND s2.created_at > s.created_at
    );

    DROP TABLE salary;
    RENAME TABLE salary_new TO salary;
    SELECT 'salary 已迁移为 9 列结构（保留每人最新一期）' AS result;
  ELSE
    SELECT 'salary 已是 9 列结构，无需迁移' AS result;
  END IF;
END //
DELIMITER ;

CALL _mig_salary_v3();
DROP PROCEDURE IF EXISTS _mig_salary_v3;
