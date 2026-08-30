# 建上月工资表
use company_agent;

CREATE TABLE if not exists `employee_salary_last_month` (
  `no` INT NOT NULL AUTO_INCREMENT COMMENT '序号',
  `employee_id` VARCHAR(10) NOT NULL COMMENT '员工工号',
  `name` VARCHAR(50) NOT NULL COMMENT '员工姓名',
  `position` VARCHAR(50) NOT NULL COMMENT '职位',
  `base_salary` DECIMAL(10,2) NOT NULL COMMENT '基本工资',
  `performance_rating` DECIMAL(3,2) NOT NULL COMMENT '绩效系数',
  `performance_bonus` DECIMAL(10,2) NOT NULL COMMENT '绩效奖金',
  `allowance` DECIMAL(10,2) NOT NULL COMMENT '补贴',
  `gross_salary` DECIMAL(10,2) NOT NULL COMMENT '应发合计',
  PRIMARY KEY (`no`),
  UNIQUE KEY `uk_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='当月工资条';

INSERT INTO employee_salary_last_month (NO, employee_id, name, position, base_salary, performance_rating, performance_bonus, allowance, gross_salary) VALUES
(1, '220401', '冯霞', '总经理', 25000.00, 0.85, 8500.00, 1500.00, 35000.00),
(2, '220402', '胡倩', '总经理助理', 15000.00, 1.00, 10000.00, 1000.00, 26000.00),
(3, '220403', '黄秀英', '商务总监', 20000.00, 1.00, 10000.00, 1200.00, 31200.00),
(4, '220404', '赵秀兰', '营销经理', 12000.00, 0.95, 9500.00, 800.00, 22300.00),
(5, '220405', '谢洋', '营销经理', 12000.00, 0.90, 9000.00, 800.00, 21800.00),
(6, '220406', '许梦', '营销专员', 8000.00, 0.80, 8000.00, 500.00, 16500.00),
(7, '220407', '李思', '营销专员', 8000.00, 0.65, 6500.00, 500.00, 15000.00),
(8, '220408', '郑磊', '运营总监', 20000.00, 1.00, 10000.00, 1200.00, 31200.00),
(9, '220409', '许磊', '调度经理', 12000.00, 0.95, 9500.00, 800.00, 22300.00),
(10, '220410', '高秀兰', '调度专员', 8000.00, 0.78, 7800.00, 500.00, 16300.00),
(11, '220411', '李洋', '调度专员', 8000.00, 0.50, 5000.00, 500.00, 13500.00),
(12, '220412', '何玲', '运营经理', 12000.00, 0.92, 9200.00, 800.00, 22000.00),
(13, '220413', '胡娟', '运营专员', 8000.00, 0.75, 7500.00, 500.00, 16000.00),
(14, '220414', '袁芬', '运营专员', 8000.00, 0.60, 6000.00, 500.00, 14500.00),
(15, '220415', '杨思', '客服经理', 12000.00, 0.90, 9000.00, 800.00, 21800.00),
(16, '220416', '董秀英', '客服专员', 8000.00, 0.76, 7600.00, 500.00, 16100.00),
(17, '220417', '傅秀英', '客服专员', 8000.00, 0.62, 6200.00, 500.00, 14700.00),
(18, '220418', '杨梦', '总车队长', 18000.00, 1.00, 10000.00, 1000.00, 29000.00),
(19, '220419', '梁怡', '车队长', 12000.00, 0.93, 9300.00, 800.00, 22100.00),
(20, '220420', '林飞', '车队长', 12000.00, 0.82, 8200.00, 800.00, 21000.00),
(21, '220421', '萧平', '车队文员', 8000.00, 0.64, 6400.00, 500.00, 14900.00),
(22, '220422', '陈平', '车队文员', 8000.00, 0.45, 4500.00, 500.00, 13000.00),
(23, '220423', '邓玲', '财务总监', 20000.00, 1.00, 10000.00, 1200.00, 31200.00),
(24, '220424', '罗强', '会计', 8000.00, 0.72, 7200.00, 500.00, 15700.00),
(25, '220425', '林伟', '出纳', 8000.00, 0.58, 5800.00, 500.00, 14300.00),
(26, '220426', '冯华', '审核', 8000.00, 0.48, 4800.00, 500.00, 13300.00);

# 建当月工资表（表中无数据，待工资条插入数据）
CREATE TABLE `employee_salary_this_month` (
  `no` INT NOT NULL AUTO_INCREMENT COMMENT '序号',
  `employee_id` VARCHAR(10) NOT NULL COMMENT '员工工号',
  `name` VARCHAR(50) NOT NULL COMMENT '员工姓名',
  `position` VARCHAR(50) NOT NULL COMMENT '职位',
  `base_salary` DECIMAL(10,2) NOT NULL COMMENT '基本工资',
  `performance_rating` DECIMAL(3,2) NOT NULL COMMENT '绩效系数',
  `performance_bonus` DECIMAL(10,2) NOT NULL COMMENT '绩效奖金',
  `allowance` DECIMAL(10,2) NOT NULL COMMENT '补贴',
  `gross_salary` DECIMAL(10,2) NOT NULL COMMENT '应发合计',
  PRIMARY KEY (`no`),
  UNIQUE KEY `uk_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='当月工资条';