"""密码哈希 + JWT 签发校验。明文密码绝不入库。"""
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import JWT_SECRET, JWT_ALG, TOKEN_EXPIRE_HOURS
from .database import get_db
from .models import Employee


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(emp: Employee) -> str:
    payload = {
        "sub": str(emp.id),
        "emp_id": emp.emp_id,
        "name": emp.name,
        "role": emp.role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Employee:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "未登录或令牌缺失")
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "令牌无效或已过期")
    emp = db.get(Employee, int(payload["sub"]))
    if emp is None:
        raise HTTPException(401, "用户不存在")
    return emp


def require_manager(user: Employee = Depends(get_current_user)) -> Employee:
    if user.role != "manager":
        raise HTTPException(403, "需要管理者权限")
    return user
