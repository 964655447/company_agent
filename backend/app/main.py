"""公司管理智能体 · 后端入口。

启动：cd backend && uvicorn app.main:app --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import assessment, attendance, auth, chat, reimbursement, roster, salary
from .seed import seed_employees


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_employees()          # 空库时自动导入花名册（26人）
    yield


app = FastAPI(title="公司管理智能体 后端", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

for r in (auth.router, attendance.router, reimbursement.router,
          salary.router, assessment.router, roster.router, chat.router):
    app.include_router(r)

@app.get("/api/health")
def health():
    return {"status": "ok"}

# 前端静态托管（放在最后，避免覆盖 /api 路由）
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
