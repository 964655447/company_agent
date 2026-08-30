"""ORM 模型 —— 字段名与 contracts/database.sql 严格对齐。"""
import json
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Date, Boolean,
    Float, UniqueConstraint, Index,
)

from .database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    no = Column(Integer, nullable=False, unique=True)
    employee_id = Column(BigInteger, nullable=False, unique=True)   # 工号，登录账号
    name = Column(String(32), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    permissions = Column(Text, nullable=False, default="[]")  # JSON 数组：可访问岗位范围
    position = Column(String(64), nullable=False)
    department = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # ---- 辅助 ----
    @property
    def permission_list(self) -> list[str]:
        try:
            v = json.loads(self.permissions)
            return v if isinstance(v, list) else []
        except Exception:
            return []

    @property
    def role(self) -> str:
        """权限覆盖多于 1 个岗位 => 管理者（与花名册层级完全吻合）。"""
        return "manager" if len(self.permission_list) > 1 else "employee"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "no": self.no, "emp_id": self.employee_id,
            "name": self.name, "permissions": self.permission_list,
            "position": self.position, "department": self.department,
            "role": self.role,
        }


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (Index("idx_att_emp_date", "employee_id", "work_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(BigInteger, nullable=False)
    checkin_time = Column(DateTime, nullable=False)
    type = Column(String(16), nullable=False)                  # clock_in / clock_out
    is_late = Column(Boolean, nullable=False, default=False)
    work_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id, "checkin_time": self.checkin_time.isoformat(),
            "type": self.type, "is_late": self.is_late,
            "work_date": self.work_date.isoformat(),
        }


class Reimbursement(Base):
    __tablename__ = "reimbursement"
    __table_args__ = (Index("idx_reimb_emp_status", "employee_id", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(BigInteger, nullable=False)
    applicant_name = Column(String(64), nullable=False, default="")  # 申请人名称（冗余存储，去外键后保留）
    category = Column(String(64), nullable=False, default="")
    amount = Column(Float, nullable=False, default=0)
    ocr_raw = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="submitted")
    approver_id = Column(Integer, nullable=True)
    submit_time = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "employee_id": self.employee_id,
            "applicant_name": self.applicant_name, "category": self.category,
            "amount": round(self.amount, 2), "status": self.status,
            "approver_id": self.approver_id,
            "submit_time": self.submit_time.isoformat(),
            "ocr_raw": self.ocr_raw or "",
        }


class EmployeeSalary(Base):
    __tablename__ = "employee_salary"

    no = Column(Integer, nullable=False)                                # 序号
    employee_id = Column(BigInteger, primary_key=True)                 # 工号（登录账号）
    name = Column(String(50), nullable=False)
    position = Column(String(50), nullable=False)
    base_salary = Column(Float, nullable=False, default=0)             # 基本工资（固定不变）
    performance_rating = Column(Float, nullable=False, default=1.0)     # 绩效系数（DECIMAL 3,2），1.0 对应奖金上限
    performance_bonus = Column(Float, nullable=False, default=0)         # 绩效奖金 = MIN(base * factor, 10000)
    allowance = Column(Float, nullable=False, default=0)                # 补贴
    gross_salary = Column(Float, nullable=False, default=0)             # 应发合计 = base + bonus + allowance

    def to_dict(self) -> dict:
        return {
            "no": self.no, "employee_id": self.employee_id, "name": self.name,
            "position": self.position,
            "base_salary": round(self.base_salary, 2),
            "performance_rating": float(self.performance_rating or 0),
            "performance_bonus": round(self.performance_bonus, 2),
            "allowance": round(self.allowance, 2),
            "gross_salary": round(self.gross_salary, 2),
        }


# 向后兼容别名：外部代码仍可用 Salary 引用
Salary = EmployeeSalary


class AssessmentLog(Base):
    __tablename__ = "assessment_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(BigInteger, nullable=False)
    position_queried = Column(String(64), nullable=False)
    queried_at = Column(DateTime, nullable=False, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "position_queried": self.position_queried,
            "queried_at": self.queried_at.isoformat(),
        }


class AssessmentStat(Base):
    __tablename__ = "assessment_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(BigInteger, nullable=False, index=True)
    original_position = Column(String(50), nullable=True)
    target_position = Column(String(50), nullable=True)
    score = Column(Float, nullable=True)
    test_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "original_position": self.original_position,
            "target_position": self.target_position,
            "score": round(self.score, 1) if self.score is not None else None,
            "test_time": self.test_time.isoformat() if self.test_time else None,
        }
