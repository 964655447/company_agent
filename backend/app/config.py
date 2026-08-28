"""全局配置。数据库切换点：改 DB_URL 一行即可（SQLite → MySQL）。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

# ---------- 数据库 ----------
# 开发期：SQLite（零安装）。上线期换成 MySQL，例如：
#   mysql+pymysql://user:pass@localhost:3306/company_agent?charset=utf8mb4
DB_URL = os.environ.get("DB_URL", f"sqlite:///{BASE_DIR / 'company.db'}")

# ---------- 认证 ----------
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production-8f3a9d")
JWT_ALG = "HS256"
TOKEN_EXPIRE_HOURS = 12

# ---------- 业务规则 ----------
WORK_START = "09:00"          # 上班时间，晚于此打卡记迟到
SUBSIDY_DEFAULT = 500.0       # 默认补贴（管理端后期可维护基数表）
PERFORMANCE_RATIO = 0.4       # 绩效基数 = 基本工资 * 0.4

# 岗位 → 基本工资基数（后端持有，不经过 Dify；管理端可扩展为表）
BASE_SALARY_MAP = {
    "总经理": 20000, "总经理助理": 12000,
    "商务总监": 15000, "运营总监": 15000, "财务总监": 15000,
    "营销经理": 10000, "调度经理": 10000, "运营经理": 10000, "客服经理": 10000,
    "总车队长": 12000, "车队长": 8000,
    "营销专员": 6000, "调度专员": 6000, "运营专员": 6000, "客服专员": 6000,
    "车队文员": 5000, "会计": 8000, "出纳": 6000, "审核": 7000,
}
BASE_SALARY_DEFAULT = 6000

# ---------- Dify 接入（AI 大脑）----------
# 未配置时所有 AI 调用走本地 fallback 规则，系统照常可跑。
# 各 Key 在 Dify 对应工作流的「访问 API」页面获取。
DIFY_BASE_URL = os.environ.get("DIFY_BASE_URL", "")        # 例 http://localhost
DIFY_KEY_WF1 = os.environ.get("DIFY_KEY_WF1", "")          # 身份意图识别
DIFY_KEY_WF2 = os.environ.get("DIFY_KEY_WF2", "")          # 报销 OCR 抽取
DIFY_KEY_WF3 = os.environ.get("DIFY_KEY_WF3", "")          # 绩效抽取与工资计算
DIFY_KEY_WF4 = os.environ.get("DIFY_KEY_WF4", "")          # 岗位知识 RAG
DIFY_KEY_WF5 = os.environ.get("DIFY_KEY_WF5", "")          # 分析报告生成
DIFY_KEY_WF6 = os.environ.get("DIFY_KEY_WF6", "")          # 考勤智能问答（悬浮气泡）
DIFY_KEY_WF7 = os.environ.get("DIFY_KEY_WF7", "")          # 员工考勤打卡（写卡+判迟到+周月统计）
DIFY_KEY_WF8 = os.environ.get("DIFY_KEY_WF8", "")          # 管理端考勤分析（按人聚合+行为分析）
DIFY_TIMEOUT = float(os.environ.get("DIFY_TIMEOUT", "60"))

# ---------- 种子数据 ----------
# 花名册 Excel 路径。默认留空：每个人的花名册在自己机器上，路径不该写进代码。
# 需要导入时在 backend/.env 里设置 ROSTER_XLSX=<你的路径> 即可。
ROSTER_XLSX = os.environ.get("ROSTER_XLSX", "")


def _load_env_file() -> None:
    """读取 backend/.env（若有），不覆盖已存在的环境变量。"""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    # 重读一次让上面的默认值拿到 .env 内容
    global DB_URL, DIFY_BASE_URL, JWT_SECRET
    global DIFY_KEY_WF1, DIFY_KEY_WF2, DIFY_KEY_WF3, DIFY_KEY_WF4, DIFY_KEY_WF5
    global DIFY_KEY_WF6, DIFY_KEY_WF7, DIFY_KEY_WF8
    if os.environ.get("DB_URL"):
        DB_URL = os.environ["DB_URL"]
    if os.environ.get("DIFY_BASE_URL"):
        DIFY_BASE_URL = os.environ["DIFY_BASE_URL"]
    if os.environ.get("JWT_SECRET"):
        JWT_SECRET = os.environ["JWT_SECRET"]
    DIFY_KEY_WF1 = os.environ.get("DIFY_KEY_WF1", DIFY_KEY_WF1)
    DIFY_KEY_WF2 = os.environ.get("DIFY_KEY_WF2", DIFY_KEY_WF2)
    DIFY_KEY_WF3 = os.environ.get("DIFY_KEY_WF3", DIFY_KEY_WF3)
    DIFY_KEY_WF4 = os.environ.get("DIFY_KEY_WF4", DIFY_KEY_WF4)
    DIFY_KEY_WF5 = os.environ.get("DIFY_KEY_WF5", DIFY_KEY_WF5)
    DIFY_KEY_WF6 = os.environ.get("DIFY_KEY_WF6", DIFY_KEY_WF6)
    DIFY_KEY_WF7 = os.environ.get("DIFY_KEY_WF7", DIFY_KEY_WF7)
    DIFY_KEY_WF8 = os.environ.get("DIFY_KEY_WF8", DIFY_KEY_WF8)


_load_env_file()
