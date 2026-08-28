-- ============================================================
-- 公司管理智能体 · 数据库契约 v0.2
-- 基准：MySQL 8.0+，字符集 utf8mb4
-- 规则：任何人改字段，必须先改本文件并发群评审，再改代码。
--       禁止在代码里私自 ALTER TABLE 或使用契约外字段。
-- 用法（同事 clone 后执行，自动建库建表）：
--   python backend/setup_mysql.py
-- ============================================================

CREATE DATABASE IF NOT EXISTS company_agent
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE company_agent;

-- ------------------------------------------------------------
-- employees 花名册（身份与权限的根表）
-- 数据来源：花名册.xlsx（26人），上线前密码必须重置为哈希值
-- ------------------------------------------------------------
CREATE TABLE employees (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  no            INT          NOT NULL UNIQUE        COMMENT '花名册序号',
  emp_id        BIGINT       NOT NULL UNIQUE        COMMENT '工号，登录账号，如 220401',
  name          VARCHAR(32)  NOT NULL               COMMENT '姓名',
  password_hash VARCHAR(255) NOT NULL               COMMENT 'argon2/bcrypt 哈希，禁止明文',
  permissions   JSON         NOT NULL               COMMENT '可访问岗位范围数组，如 ["总经办","商务部"]',
  position      VARCHAR(64)  NOT NULL               COMMENT '岗位',
  department    VARCHAR(64)  NOT NULL               COMMENT '所属部门',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_emp_name (name),
  INDEX idx_emp_dept (department)
) COMMENT='花名册';

-- ------------------------------------------------------------
-- attendance 考勤
-- ------------------------------------------------------------
CREATE TABLE attendance (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  employee_id  INT      NOT NULL                     COMMENT '员工id → employees.id',
  checkin_time DATETIME NOT NULL                     COMMENT '打卡时间',
  type         ENUM('clock_in','clock_out') NOT NULL  COMMENT '上班/下班',
  is_late      BOOLEAN  NOT NULL DEFAULT FALSE       COMMENT '是否迟到',
  work_date    DATE     NOT NULL                     COMMENT '考勤日期',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_att_emp FOREIGN KEY (employee_id) REFERENCES employees(id),
  INDEX idx_att_emp_date (employee_id, work_date)
) COMMENT='考勤';

-- ------------------------------------------------------------
-- reimbursement 费用报销（含审批状态机）
-- 状态流：draft → submitted → approving → approved / rejected
-- ------------------------------------------------------------
CREATE TABLE reimbursement (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  employee_id  INT           NOT NULL                 COMMENT '申请人 → employees.id',
  category     VARCHAR(64)   NOT NULL                 COMMENT '报销类目',
  amount       DECIMAL(10,2) NOT NULL                 COMMENT '金额',
  ocr_raw      TEXT          NULL                     COMMENT 'OCR 原始识别内容(JSON字符串)',
  status       ENUM('draft','submitted','approving','approved','rejected')
               NOT NULL DEFAULT 'submitted'            COMMENT '审批状态',
  approver_id  INT           NULL                     COMMENT '审批人 → employees.id',
  submit_time  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_reimb_emp  FOREIGN KEY (employee_id)  REFERENCES employees(id),
  CONSTRAINT fk_reimb_appr FOREIGN KEY (approver_id) REFERENCES employees(id),
  INDEX idx_reimb_emp_status (employee_id, status)
) COMMENT='费用报销';

-- ------------------------------------------------------------
-- salary 工资核算表（扁平快照，字段严格按用户指定 v2：
--   NO, ID, name, position, base_salary, performance_rating,
--   performance_bonus, allowance, gross_salary）
-- ID = 工号（登录账号），为每行主键；gross_salary = base_salary + performance_bonus + allowance
-- ------------------------------------------------------------
CREATE TABLE salary (
  no                 INT           NOT NULL            COMMENT '序号（花名册序号）→ employees.no',
  id                 BIGINT        NOT NULL PRIMARY KEY COMMENT '工号（ID，登录账号）→ employees.emp_id',
  name               VARCHAR(32)   NOT NULL            COMMENT '姓名',
  position           VARCHAR(64)   NOT NULL            COMMENT '岗位',
  base_salary        DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '基本工资',
  performance_rating VARCHAR(8)    NOT NULL DEFAULT 'C' COMMENT '绩效评级 S/A/B/C/D',
  performance_bonus  DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '绩效奖金',
  allowance          DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '津贴/补贴',
  gross_salary       DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '应发工资 = 基本+绩效奖金+津贴'
) COMMENT='工资核算表';

-- ------------------------------------------------------------
-- assessment_log 进阶考核查询日志
-- ------------------------------------------------------------
CREATE TABLE assessment_log (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  employee_id      INT         NOT NULL               COMMENT '员工id',
  position_queried VARCHAR(64) NOT NULL               COMMENT '查询的岗位',
  queried_at       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_asl_emp FOREIGN KEY (employee_id) REFERENCES employees(id),
  INDEX idx_asl_emp (employee_id)
) COMMENT='考核查询日志';
