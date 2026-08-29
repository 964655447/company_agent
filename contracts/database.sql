-- ============================================================
-- 公司管理智能体 · 数据库 Schema
-- 由 setup_mysql.py 执行（CREATE TABLE IF NOT EXISTS，幂等可重复跑）。
-- 字段名需与 backend/app/models.py 严格对齐。
-- 最近变更：reimbursement 表去掉 employee_id / approver_id 两个外键，
--           并在 employee_id 后新增 applicant_name VARCHAR(64) NOT NULL。
-- ============================================================

CREATE TABLE IF NOT EXISTS `employees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `no` int NOT NULL COMMENT '花名册序号',
  `emp_id` bigint NOT NULL COMMENT '工号，登录账号，如 220401',
  `name` varchar(32) NOT NULL COMMENT '姓名',
  `password_hash` varchar(255) NOT NULL COMMENT 'argon2/bcrypt 哈希，禁止明文',
  `permissions` json NOT NULL COMMENT '可访问岗位范围数组，如 ["总经办","商务部"]',
  `position` varchar(64) NOT NULL COMMENT '岗位',
  `department` varchar(64) NOT NULL COMMENT '所属部门',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `no` (`no`),
  UNIQUE KEY `emp_id` (`emp_id`),
  UNIQUE KEY `uk_emp_name` (`name`),
  KEY `idx_emp_dept` (`department`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='花名册';

CREATE TABLE IF NOT EXISTS `attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL COMMENT '员工id → employees.id',
  `checkin_time` datetime NOT NULL COMMENT '打卡时间',
  `type` enum('clock_in','clock_out') NOT NULL COMMENT '上班/下班',
  `is_late` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否迟到',
  `work_date` date NOT NULL COMMENT '考勤日期',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_att_emp_date` (`employee_id`,`work_date`),
  CONSTRAINT `fk_att_emp` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='考勤';

CREATE TABLE IF NOT EXISTS `reimbursement` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL COMMENT '申请人 → employees.id',
  `applicant_name` varchar(64) NOT NULL COMMENT '申请人名称',
  `category` varchar(64) NOT NULL COMMENT '报销类目',
  `amount` decimal(10,2) NOT NULL COMMENT '金额',
  `ocr_raw` text COMMENT 'OCR 原始识别内容(JSON字符串)',
  `status` enum('draft','submitted','approving','approved','rejected') NOT NULL DEFAULT 'submitted' COMMENT '审批状态',
  `approver_id` int DEFAULT NULL COMMENT '审批人 → employees.id',
  `submit_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_reimb_appr` (`approver_id`),
  KEY `idx_reimb_emp_status` (`employee_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='费用报销';

CREATE TABLE IF NOT EXISTS `employee_salary` (
  `no` int NOT NULL COMMENT '序号',
  `id` varchar(10) NOT NULL COMMENT '员工工号',
  `name` varchar(50) NOT NULL COMMENT '员工姓名',
  `position` varchar(50) NOT NULL COMMENT '职位',
  `base_salary` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '基本工资(固定不变)',
  `performance_rating` decimal(3,2) NOT NULL COMMENT '绩效系数，1.0对应奖金上限10000',
  `performance_bonus` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '绩效奖金 MIN(base_salary*performance_factor,10000)',
  `allowance` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '补贴',
  `gross_salary` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '应发合计 = base_salary + performance_bonus + allowance',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_no` (`no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='员工薪资绩效表';

CREATE TABLE IF NOT EXISTS `assessment_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `employee_id` int NOT NULL COMMENT '员工id',
  `position_queried` varchar(64) NOT NULL COMMENT '查询的岗位',
  `queried_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_asl_emp` (`employee_id`),
  CONSTRAINT `fk_asl_emp` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='考核查询日志';
