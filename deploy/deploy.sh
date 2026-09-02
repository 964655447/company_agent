#!/bin/bash
# ============================================================
#  company_agent 阿里云 ECS 一键部署脚本
#  目标环境：Debian 12.x / 2vCPU 2GB / 公网 IP 可直连
#  用法：sudo bash deploy.sh
# ============================================================
set -euo pipefail

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 必须 root ──
[[ $EUID -eq 0 ]] || error "请用 sudo 运行：sudo bash $0"

# ── 配置（按需修改）─────────────────────────────────────
PROJECT_DIR="/opt/company_agent"          # 项目部署路径
PYTHON="python3"                          # Python 命令
APP_PORT=9000                            # 启动器端口（前端+API统一入口）
BACKEND_PORT=8000                        # 后端 FastAPI 端口（仅内网）
MYSQL_ROOT_PASSWORD="Company_Agent_2026!" # MySQL root 密码（请改！）
MYSQL_DB_NAME="company_agent"            # 数据库名
JWT_SECRET="$(head -c 16 /dev/urandom | xxd -p)"  # 随机 JWT 密钥
# ───────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo "  company_agent 阿里云 ECS 部署"
echo "  目标: ${PROJECT_DIR}"
echo "  访问: http://$(curl -s ifconfig.me):${APP_PORT}/fe/"
echo "============================================================"
echo ""

# ═══ Step 1: 系统更新 + 基础依赖 ═══
echo -e "\n${CYAN}[1/7] 系统更新 & 安装基础依赖...${NC}"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl nginx ufw \
    default-mysql-server default-mysql-client build-essential > /dev/null 2>&1
info "基础依赖安装完成"

# ═══ Step 2: MySQL 初始化 ═══
echo -e "\n${CYAN}[2/7] 配置 MySQL...${NC}"

# 启动 MySQL
service mysql start || true
systemctl enable mysql > /dev/null 2>&1

# 设置 root 密码 & 创建数据库
mysql -u root <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PASSWORD}';
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
FLUSH PRIVILEGES;
SQL
info "MySQL root 密码已设置 · 数据库 ${MYSQL_DB_NAME} 已创建"

# ═══ Step 3: 部署项目代码 ═══
echo -e "\n${CYAN}[3/7] 克隆/更新项目代码...${NC}"

if [ -d "${PROJECT_DIR}/.git" ]; then
    cd "$PROJECT_DIR" && git pull --ff-only origin main
else
    rm -rf "$PROJECT_DIR"
    git clone https://github.com/Luo-JB/company_agent.git "$PROJECT_DIR"
fi
cd "$PROJECT_DIR"
info "代码已部署到 ${PROJECT_DIR}"

# ═══ Step 4: Python 虚拟环境 + 依赖 ═══
echo -e "\n${CYAN}[4/7] 创建 Python 虚拟环境 & 安装依赖...${NC}"

cd "${PROJECT_DIR}/backend"
$PYTHON -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate
info "Python 虚拟环境就绪 (venv)"

# ═══ Step 5: 写 .env 配置 ═══
echo -e "\n${CYAN}[5/7] 生成后端配置 (.env)...${NC}"

cat > "${PROJECT_DIR}/backend/.env" <<EOF
# ── 数据库（ECS 本地 MySQL）──
DB_URL=mysql+pymysql://root:${MYSQL_ROOT_PASSWORD}@127.0.0.1:3306/${MYSQL_DB_NAME}

# ── JWT ──
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ── Dify（ECS 不部署，留空走本地兜底）──
DIFY_AGENT_KEY=
DIFY_BASE_URL=

# ── 其他 ──
UPLOAD_DIR=./uploads
EOF
chmod 600 "${PROJECT_DIR}/backend/.env"
info ".env 已生成 (Dify 留空 → AI 走本地兜底规则)"

# ═══ Step 6: 建表 + 导入种子数据 ═══
echo -e "\n${CYAN}[6/7] 初始化数据库（建表 + 种子数据）...${NC}"

cd "${PROJECT_DIR}/backend"
source venv/bin/activate

# 建所有表（含 assessment_stats 等）
$PYTHON -c "
from app.main import Base
from app.database import engine_sync
Base.metadata.create_all(engine_sync)
print('表结构已创建')
"

# 导入种子数据（26 名演示员工 + 考勤/报销/考核日志等）
if [ -f "seed.py" ]; then
    $PYTHON seed.py 2>/dev/null && info "种子数据已导入（26 名员工）" || warn "seed.py 执行跳过（可能数据已存在）"
fi

# 如果有 setup_mysql.py 也跑一下
if [ -f "setup_mysql.py" ]; then
    $PYTHON setup_mysql.py 2>/dev/null || true
fi

deactivate
info "数据库初始化完成"

# ═══ Step 7: systemd 服务（开机自启）═══
echo -e "\n${CYAN}[7/7] 注册 systemd 服务（开机自启）...${NC}"

# 先杀掉可能存在的旧进程
pkill -f "uvicorn app.main:app.*--port ${BACKEND_PORT}" 2>/dev/null || true
pkill -f "launcher.py.*${APP_PORT}" 2>/dev/null || true
sleep 1

# ── 后端服务 ──
cat > /etc/systemd/system/company-backend.service <<EOF
[Unit]
Description=Company Agent Backend (FastAPI)
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}/backend
Environment="PATH=${PROJECT_DIR}/backend/venv/bin:/usr/bin:/usr/local/bin"
ExecStart=${PROJECT_DIR}/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 启动器服务（前端 + 反代后端 API）──
cat > /etc/systemd/system/company-launcher.service <<EOF
[Unit]
Description=Company Agent Launcher (Frontend + Reverse Proxy)
After=network.target company-backend.service
Requires=company-backend.service

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=/usr/bin:/usr/local/bin:${PROJECT_DIR}/backend/venv/bin"
ExecStart=/usr/bin/python3 launcher/launcher.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable company-backend company-launcher
systemctl start company-backend

# 等后端起来
echo -n "  等待后端启动"
for i in $(seq 1 15); do
    sleep 1
    if curl -s -m 2 "http://127.0.0.1:${BACKEND_PORT}/api/chat/status" >/dev/null 2>&1; then
        echo " ✓ (${i}s)"
        break
    fi
    echo -n "."
done

systemctl start company-launcher

# 等启动器起来
echo -n "  等待启动器启动"
for i in $(seq 1 10); do
    sleep 1
    if curl -s -m 2 "http://127.0.0.1:${APP_PORT}/fe/" >/dev/null 2>&1; then
        echo " ✓ (${i}s)"
        break
    fi
    echo -n "."
done

systemctl status company-backend --no-pager -l | head -5
systemctl status company-launcher --no-pager -l | head -5

# ═══ 防火墙提示 ═══
PUBLIC_IP=$(curl -s -m 5 ifconfig.me 2>/dev/null || echo "你的公网IP")

echo ""
echo "============================================================"
echo -e "${GREEN}  🎉 部署完成！${NC}"
echo "============================================================"
echo ""
echo "  访问地址:  ${CYAN}http://${PUBLIC_IP}:${APP_PORT}/fe/${NC}"
echo "  测试账号:  工号 220401 / 密码 123456"
echo ""
echo "  常用命令:"
echo "    查看日志:  journalctl -u company-launcher -f"
echo "    重启服务:  systemctl restart company-launcher"
echo "    查看状态:  systemctl status company-launcher"
echo "    后端日志:  journalctl -u company-backend -f"
echo ""
echo "  ⚠️  还需手动操作（阿里云控制台）："
echo "     1. 安全组 → 入方向 → 添加规则 → 放行 TCP ${APP_PORT} 端口"
echo "        （授权对象: 0.0.0.0/0 或你的 IP）"
echo "     2. 如需 SSH: 放行 TCP 22 端口"
echo ""
echo "  MySQL 信息:"
echo "    root 密码: ${MYSQL_ROOT_PASSWORD}"
echo "    数据库:   ${MYSQL_DB_NAME}"
echo "    连接:     mysql -u root -p'${MYSQL_ROOT_PASSWORD}' ${MYSQL_DB_NAME}"
echo "============================================================"
