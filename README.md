# 公司管理智能体（company_agent）

一个本地部署的公司内部 AI 助手系统，覆盖**考勤、报销、工资、考核**四大模块，并集成了 Dify 统一智能体提供自然语言问答与自动出报告能力。前端还内置一个可拖拽、带物理效果的「桌宠」交互。

> ⚠️ 演示性质项目：仓库内置的花名册、演示数据、登录密码均为随机生成的**演示数据**，非真实员工信息。

---

## 一、技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy + PyMySQL + JWT(bcrypt) |
| 前端 | 原生 HTML / CSS / JavaScript（无框架） |
| 数据库 | MySQL 8.0+ |
| AI | Dify 统一智能体（Agent + 工作流工具） |
| 启动器 | Python 标准库 `http.server`（单文件，零额外依赖） |

---

## 二、目录结构

```
company/
├── backend/                # 后端（FastAPI，端口 8000）
│   ├── app/
│   │   ├── main.py         # 入口：挂载路由、启动建表、托管前端静态
│   │   ├── config.py       # 读 .env 配置
│   │   ├── database.py     # SQLAlchemy 引擎 / Session
│   │   ├── models.py       # ORM 模型
│   │   ├── dify_client.py  # 统一智能体适配器 call_dify_agent()
│   │   ├── security.py     # JWT 签发 / 校验
│   │   ├── seed.py         # 空库时自动导入花名册
│   │   ├── local_rules.py  # 本地降级规则（Dify 不可用时的兜底）
│   │   └── routers/        # 各业务路由
│   │       ├── auth.py         # 登录
│   │       ├── attendance.py   # 考勤
│   │       ├── reimbursement.py# 报销
│   │       ├── salary.py       # 工资
│   │       ├── assessment.py   # 考核 / 出题
│   │       ├── roster.py       # 花名册
│   │       └── chat.py         # Dify 智能助手
│   ├── setup_mysql.py      # 一键建库建表 + 生成演示数据
│   ├── requirements.txt
│   ├── start.bat           # 双击启动后端
│   └── .env.example        # 配置模板（复制为 .env 后填写）
│
├── frontend/               # 纯原生前端
│   ├── index.html          # 入口（登录页 + 主界面 + 桌宠 + 对话气泡）
│   ├── js/app.js           # 全部前端逻辑（登录、路由、桌宠物理、对话）
│   ├── css/style.css       # 样式
│   └── assets/pet/frames/  # 桌宠动画帧（约 760 张 PNG，已入库）
│
├── launcher/               # 可视化启动器（端口 9000）
│   ├── launcher.py         # 仪表盘 + 同源托管前端 /fe/ + 一键启停后端
│   ├── launcher.bat        # 双击运行
│   └── stopper.py / stopper.bat
│
└── contracts/
    ├── database.sql            # 建表 DDL（6 张核心表）
    ├── assessment_stats_seed.sql
    └── dify/                   # Dify 工作流导入文件
        ├── 导入与接线清单.md
        ├── 进阶考核管理端_导入版.yml      # 考核报告（查 assessment_stats）
        ├── Test evaluation_导入版.yml     # 试卷阅卷（查 employees + 上传 Word）
        └── job_description and test_generation_导入版.yml  # 岗位出题（查知识库）
```

---

## 三、环境准备

- **Python 3.10+**（启动器会自动识别 Anaconda / venv / `py -3`，无需写死路径）
- **MySQL 8.0+**（本机启动，默认 `127.0.0.1:3306`，root 密码自备）
- **（可选）Dify**：Docker 部署，用于 AI 问答 / 自动报告。不装也能跑基础功能（走本地兜底）

---

## 四、快速开始

### 方式 A：启动器（推荐，一键启动全部）

```bash
# 1. 进入启动器目录
cd launcher

# 2. 运行（或双击 launcher.bat）
python launcher.py
```

启动后自动打开浏览器到 `http://localhost:9000`：

1. **首次配置**：页面会显示「数据库配置」向导，填写本机 MySQL 信息（主机 / 端口 / 用户名 / 密码 / 库名）和可选的 Dify Key，提交后自动建库建表。
2. **一键启动**：在仪表盘点「启动」拉起后端（8000），或直接点「打开前端页面」访问 `http://localhost:9000/fe/index.html`。
3. 仪表盘实时显示 MySQL / 后端 / Dify 三个服务的运行状态。

> 启动器同时托管前端（`/fe/`），与后端同源，规避 `file://` 的 CORS 问题。

### 方式 B：手动启动后端 + 前端

```bash
# 1. 准备后端配置
cd backend
cp ../.env.example .env          # 然后编辑 .env 填 DB_URL / DIFY_AGENT_KEY
pip install -r requirements.txt  # 或用 Anaconda 环境

# 2. 初始化数据库（建库 + 8 张表，幂等可重复跑）
python setup_mysql.py
python setup_mysql.py --seed-demo   # 可选：生成演示数据（26 名员工 + 考勤/薪资/报销/考核）

# 3. 启动后端（前端静态目录也会挂载在 8000 根路径）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
#   或双击 start.bat
```

- 后端接口文档：`http://localhost:8000/docs`
- 前端页面：`http://localhost:8000/`（后端根路径已托管 `frontend/`），或 `http://localhost:9000/fe/index.html`（经启动器）

> 演示账号：工号 `220401` ~ `220426`，密码统一 `123456`。

---

## 五、配置说明（backend/.env）

`.env` 被 git 忽略，**不会**随仓库分发，每位协作者需自行创建。模板见 `backend/.env.example`：

```ini
# ---- 统一智能体（Dify Agent）----
# 在 Dify 创建 Agent 类型应用 → 添加工作流工具 → 发布 → 复制 API Key
DIFY_BASE_URL=http://localhost/v1
DIFY_AGENT_KEY=

# ---- 数据库（MySQL）----
DB_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/company_agent

# ---- 安全 ----
JWT_SECRET=请改成你自己的随机串
```

| 变量 | 说明 |
|---|---|
| `DIFY_BASE_URL` | Dify 的 API 地址。**同机**部署写 `http://localhost/v1`；Dify 在别的机器写其局域网 IP（如 `http://10.254.3.x/v1`） |
| `DIFY_AGENT_KEY` | Dify「公司」Agent 的 API Key。**留空则 AI 问答走本地兜底**，其余功能照常可用 |
| `DB_URL` | SQLAlchemy 连接串，指向你的 MySQL 实例与 `company_agent` 库 |
| `JWT_SECRET` | JWT 签发密钥，生产环境务必修改 |

---

## 六、前端（Frontend）

纯原生 HTML/CSS/JS，**不依赖任何前端框架或构建工具**，改完刷新即生效。

- **入口**：`frontend/index.html`（登录页 + 主界面 + 桌宠 + 智能助手气泡）
- **逻辑**：`frontend/js/app.js`（登录鉴权、页面路由、桌宠物理引擎、与后端 `/api/*` 通信）
- **样式**：`frontend/css/style.css`
- **桌宠素材**：`frontend/assets/pet/frames/`（idle / dance / walk / sleep / push 等动作帧，角色高已统一为 151px）

**访问方式**：经启动器 `9000/fe/index.html` 或后端 `8000/`（同源，无跨域问题）。

**主要功能界面**：
- 登录（工号 + 密码，JWT 存 localStorage）
- 考勤查询、报销、工资条、考核成绩展示
- 右下角「智能助手」气泡 → 调 Dify 自然语言问答 / 生成考核报告 / 出岗位试卷
- 可拖拽、带重力与边缘反弹的桌宠，单击弹出可 8 向缩放的对话面板

---

## 七、后端（Backend）

FastAPI 应用，端口 `8000`。核心逻辑：

- **入口** `app/main.py`：注册路由、启动时 `Base.metadata.create_all` 幂等建表、挂载前端静态目录、`/api/health` 健康检查。
- **统一智能体适配** `app/dify_client.py`：所有 AI 请求汇聚到 `call_dify_agent()`，调用 Dify `/v1/chat-messages`（Agent 仅支持 `streaming` 模式）。未配置 Key 或调用失败时，按 `local_rules.py` 本地降级。
- **业务路由**（`app/routers/`）：考勤、报销、工资、考核、花名册、登录、智能助手。

**依赖**（`requirements.txt`）：`fastapi`、`uvicorn[standard]`、`sqlalchemy`、`pyjwt`、`bcrypt`、`python-multipart`、`httpx`、`openpyxl`、`pymysql`。

> 注：代码自行解析 `.env`（不依赖 python-dotenv），`.env` 不会覆盖已存在的系统环境变量。

### API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 工号 + 密码登录，返回 JWT |
| GET | `/api/health` | 健康检查（启动器据此判断后端存活）|
| POST | `/api/chat` | 智能助手对话（统一走 Dify Agent）|
| GET | `/api/chat/status` | 返回 `{"dify":{"enabled":true/false}}`，判断是否已接入 Dify |
| GET/POST | `/api/attendance/*` | 考勤查询（`/ask` 为自然语言问答）|
| GET/POST | `/api/reimbursement/*` | 报销 |
| GET/POST | `/api/salary/*` | 工资条 |
| GET/POST | `/api/assessment/*` | 考核成绩 / 出卷 |
| GET | `/api/roster/*` | 花名册 |

完整接口见 `http://localhost:8000/docs`（Swagger）。

---

## 八、数据库（Database）

**MySQL 8.0+**，库名 `company_agent`。

### 初始化

```bash
cd backend
python setup_mysql.py                  # 建库 + 建表（幂等，已存在则跳过）
python setup_mysql.py --seed-demo     # 生成演示数据（幂等；--reset 先清空再灌）
python setup_mysql.py --seed-employees # 从花名册.xlsx 导入真实员工（需设 ROSTER_XLSX 环境变量）
```

启动器「保存并初始化数据库」按钮等价于上面的建库建表步骤。

### 数据表（共 8 张）

| 表 | 用途 |
|---|---|
| `employees` | 员工主表（工号、姓名、密码哈希、部门、职位、权限）|
| `attendance` | 考勤打卡记录 |
| `reimbursement` | 报销单 |
| `employee_salary` | 当月工资条 |
| `assessment_log` | 考核查询日志 |
| `assessment_stats` | 考核成绩（Dify 工作流读写）|
| `employee_salary_last_month` | 上月工资条（含 26 行演示数据）|
| `employee_salary_this_month` | 当月工资条（待 Dify 工作流插入）|

> 员工标识统一使用**工号 `employee_id`**（真实工号 220401+），`employees.id` 仅为内部自增主键，不作为业务标识。

### 演示数据

`--seed-demo` 会生成 26 名演示员工（冯霞 220401 ~ 冯华 220426，密码 `123456`）、近 3 个月考勤、工资、报销、考核成绩等，全部幂等（非空表跳过）。

---

## 九、Dify 智能体接入

系统只认**一个 Dify 统一智能体（Agent）**，通过 `.env` 的两个变量接入，不需要为每个工作流单独配 Key。

### 架构

```
前端智能助手气泡 ──POST /api/chat──▶ 后端 dify_client.call_dify_agent()
                                         │
                                         ▼
                              Dify「公司」Agent（对话型应用）
                                         │ 挂载工具
                    ┌────────────────────┼────────────────────┐
                考核报告工具          试卷阅卷工具          岗位出题工具
                （查 MySQL）         （查 MySQL+Word）     （查知识库）
```

### 部署步骤（详见 `contracts/dify/导入与接线清单.md`）

1. **起 Dify**：Docker Compose 部署（默认占 80 端口，与 Steam++ 等抢端口时需改映射）。
2. **装插件**：`junjiem/db_query`（连库）、`bowenliang123/md_exporter`（Word 导出，岗位出题用）。
3. **导入工作流**：从 `contracts/dify/` 导入 3 份 `*_导入版.yml`，逐个预览运行确认不报红。
4. **建知识库**（仅岗位出题）：上传岗位文档，替换工作流里的 `dataset_ids`。
5. **发布为工具**：每个工作流 → 发布 → 「作为工具发布」。
6. **建 Agent**：新建 **Agent 类型**应用 → 挂上 3 个工具 → 写路由提示词 → 发布。
7. **拿 Key**：Agent → API 访问 → 生成 Key，填入 `backend/.env` 的 `DIFY_AGENT_KEY`。

### ⚠️ 关键坑（接不通几乎都在这）

- **应用类型必须是 Agent，不是 Workflow**。后端调的是 `/v1/chat-messages`，Workflow 应用没有这个端点。
- **db_query 连接参数必须设为「常量」**：在 Dify UI 里把工作流 db_query 节点的 `db_host / db_port / db_name / db_username / db_password / db_type` 从「由模型自动填写」改为「常量」，填写：
  - `host.docker.internal` / `3306` / `company_agent` / `root` / `<你的MySQL密码>` / `mysql`
  - 仓库里 3 份 YAML 已固化这些值为常量（host 用 `host.docker.internal`），重新导入即用。
  - 原因：Agent 模式下 LLM 会把 host 自动填成 `localhost`，容器内连不到宿主 MySQL，报"访问被拒绝"。
- **Agent 模型 Key 要配好**：若 Dify 报 `Incorrect API key provided`，通常是 Agent 内部 LLM 模型的 Key 没配/失效，不是应用 Key 的问题。
- **MySQL 可达性**：Dify 容器通过 `host.docker.internal:3306` 连宿主 MySQL；同事机器上需确保其 MySQL 允许该连接（默认 `root@'%'` 即可）。

### 验证

```bash
# 后端是否读到 Key
curl -s http://localhost:8000/api/chat/status
# → {"dify":{"enabled":true,...}}

# 发一条真实问题
curl -s -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <登录token>" \
  -H "Content-Type: application/json" \
  -d '{"message":"生成 220401 的考核报告"}'
# → "ai":true 且 reply 有实质内容 = 全链路通
```

---

## 十、常见问题

**Q：启动器点「启动」后端没起来？**
A：看 `backend/launcher_backend.log`。常见原因：Python 缺 `uvicorn`（启动器会自动 `pip install -r requirements.txt`）、或 8000 端口被占用。

**Q：AI 问答返回「尚未接入」/「智能体未返回内容」？**
A：`/api/chat/status` 若 `enabled:false` → `.env` 没填 Key 或没重启后端；若 `enabled:true` 但仍无内容 → Dify 侧工作流/工具没配好（见第九节）。

**Q：生成考核报告报「数据库连接被拒绝」？**
A：Dify 工作流的 db_query 参数没固化成常量（host 被填成 `localhost`）。按第九节把参数改为常量 `host.docker.internal` 即可。

**Q：前端打开是白屏 / 接口 404？**
A：必须通过启动器 `9000/fe/` 或后端 `8000/` 访问，不要直接双击 `index.html`（`file://` 会有跨域问题）。

**Q：同事拉代码后需要改什么？**
A：代码零改动。只需在本机创建 `backend/.env`（填自己的 `DB_URL` 和 `DIFY_AGENT_KEY`），并确保 MySQL / Dify 环境就绪。`company_agent` 仅是演示库名，可自定义。

---

## 十一、协作与部署提示

- 仓库已 `.gitignore` 忽略 `backend/.env`、`backend/company.db`、`.idea/` 等，敏感配置不进库。
- 前端桌宠帧 `frontend/assets/pet/frames/` 已入库（约 21MB），协作者 `git pull` 即完整。
- 推送用 SSH over 443：`git@ssh.github.com:964655447/company_agent.git`。
- 项目长期记忆见 `.workbuddy/memory/`。
