# company_agent 阿里云 ECS 部署指南

> **目标服务器**: Debian 12.10 / 2vCPU 2GB / 公网 IP: 39.106.199.157
> **访问方式**: http://39.106.199.157:9000/fe/
> **测试账号**: 工号 `220401` / 密码 `123456`

---

## 一、阿里云控制台操作（必须先做）

### 1. 放行安全组端口

进入 **ECS 控制台 → 安全组 → 入方向规则 → 添加规则**：

| 端口 | 授权对象 | 用途 |
|------|---------|------|
| **22** | 你的IP/32 或 0.0.0.0/0 | SSH 远程连接 |
| **9000** | 0.0.0.0/0 | 启动器（前端+API统一入口） |

> ⚠️ 8000 端口**不需要放行**——后端只监听 127.0.0.1，通过启动器内部转发。

### 2. SSH 连接服务器

```bash
ssh root@39.106.199.157
```

---

## 二、一键部署

把部署脚本传到服务器上执行：

```bash
# 方式 A：直接从 GitHub 拉脚本
curl -fsSL https://raw.githubusercontent.com/Luo-JB/company_agent/main/deploy/deploy.sh -o /tmp/deploy.sh && sudo bash /tmp/deploy.sh

# 方式 B：本地 SCP 上传后执行
scp G:\AI\company\deploy\deploy.sh root@39.106.199.157:/tmp/
ssh root@39.106.199.157 "sudo bash /tmp/deploy.sh"
```

脚本会自动完成：
1. ✅ apt 更新 + 安装 Python3 / Git / MySQL / Nginx
2. ✅ MySQL 初始化（设 root 密码、建库）
3. ✅ 克隆项目代码到 `/opt/company_agent`
4. ✅ 创建 Python venv + 安装 pip 依赖
5. ✅ 生成 `.env` 配置文件
6. ✅ 建表 + 导入种子数据（26 名演示员工）
7. ✅ 注册 systemd 服务（开机自启、崩溃重启）

---

## 三、部署后验证

```bash
# 检查两个服务状态
systemctl status company-launcher --no-pager -l
systemctl status company-backend  --no-pager -l

# 看实时日志
journalctl -u company-launcher -f

# 测试 API 是否通
curl http://127.0.0.1:9000/fe/index.html   # 前端页面
curl http://127.0.0.1:9000/api/chat/status # 后端 API（需带 token）
```

浏览器打开：**http://39.106.199.157:9000/fe/**

---

## 四、常用运维命令

| 操作 | 命令 |
|------|------|
| 重启全部服务 | `systemctl restart company-backend company-launcher` |
| 只重启后端 | `systemctl restart company-backend` |
| 只重启前端 | `systemctl restart company-launcher` |
| 查看后端日志 | `journalctl -u company-backend -f` |
| 查看启动器日志 | `journalctl -u company-launcher -f` |
| 停止服务 | `systemctl stop company-backend company-launcher` |
| 启动服务 | `systemctl start company-backend company-launcher` |
| MySQL 登录 | `mysql -u root -p'Company_Agent_2026!' company_agent` |

---

## 五、更新代码

```bash
cd /opt/company_agent
git pull origin main

# 如果有新依赖：
cd backend && source venv/bin/activate && pip install -r requirements.txt && deactivate

# 重启生效
systemctl restart company-backend company-launcher
```

---

## 六、架构说明

```
用户浏览器
    │
    ▼  HTTP :9000
┌─────────────────────────────┐
│   Launcher (Python HTTP)     │  ← systemd: company-launcher
│   · 托管前端静态文件 /fe/*   │
│   · 反代 /api/* → :8000     │
│   · 仪表盘 / (Dashboard)     │
└──────────┬──────────────────┘
           │  127.0.0.1:8000
           ▼
┌─────────────────────────────┐
│   FastAPI Backend            │  ← systemd: company-backend
│   · JWT 鉴权                 │
│   · 考勤/考核/岗位查询       │
│   · AI 本地兜底（无 Dify）   │
└──────────┬──────────────────┘
           │  127.0.0.1:3306
           ▼
┌─────────────────────────────┐
│   MySQL                      │
│   company_agent 数据库        │
│   26 名演示员工              │
└─────────────────────────────┘
```

---

## 七、注意事项

1. **内存**：2G 跑 MySQL + FastAPI + Launcher 够用，但不要在这台机器上跑 Dify/Docker
2. **MySQL root 密码**：脚本默认 `Company_Agent_2026!`，部署前请修改 `deploy.sh` 顶部的 `MYSQL_ROOT_PASSWORD`
3. **JWT_SECRET**：脚本随机生成，每次部署不同。如需固定可改 `deploy.sh`
4. **Dify**：`.env` 里留空 = AI 走本地兜底规则。后续要接 Dify 只需填 `DIFY_AGENT_KEY` + `DIFY_BASE_URL`
5. **防火墙**：如果开了 ufw，确保 `ufw allow 9000` 和 `ufw allow 22`
6. **备份**：定期 `mysqldump` 数据库到 OSS 或本地
