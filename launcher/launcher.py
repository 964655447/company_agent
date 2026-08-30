# -*- coding: utf-8 -*-
"""
公司管理智能体 · 可视化启动器
-------------------------------------------------
单文件启动器（仅依赖 Python 标准库）：
  - 在 9000 端口提供可视化仪表盘，展示 MySQL / 后端 / Dify 三个服务的运行状态
  - 一键启动 / 停止 FastAPI 后端（8000）
  - 同时托管前端静态目录 /fe/（同源，规避 file:// 的 CORS 问题）
  - 自动打开浏览器到仪表盘

用法：
  python launcher.py                 # 直接运行
  或双击同目录的 launcher.bat
"""
import http.server
import socketserver
import subprocess
import threading
import json
import webbrowser
import os
import sys
import socket
import urllib.request
import urllib.error
import urllib.parse
import re
from datetime import datetime
from pathlib import Path

# ============================ 配置（全部相对定位，克隆到任意路径都能用）============================
BACKEND_PORT = 8000
DASHBOARD_PORT = 9000
LAUNCHER_DIR = Path(__file__).resolve().parent
ROOT_DIR = LAUNCHER_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
# 运行启动器的 python 即用来跑后端；如需指定虚拟环境，可设环境变量 COMPANY_PYTHON
def _resolve_python():
    """挑选一个能 import 后端依赖（uvicorn/sqlalchemy/pymysql/fastapi）的 python。
    优先级：COMPANY_PYTHON > 启动器自身 python > backend venv > 常见 Anaconda 安装 >
            Windows py -3 启动器 > 回退系统 python（并打警告）。
    关键：所有候选都不含依赖时，绝不能再悄悄回退到没依赖的 python，否则后端会秒崩。
    """
    raw = []
    if os.environ.get("COMPANY_PYTHON"):
        raw.append(os.environ["COMPANY_PYTHON"])
    raw.append(sys.executable)
    for v in (BACKEND_DIR / "venv" / "Scripts" / "python.exe",
              BACKEND_DIR / ".venv" / "Scripts" / "python.exe",
              BACKEND_DIR / "venv" / "bin" / "python",
              BACKEND_DIR / ".venv" / "bin" / "python"):
        if v.exists():
            raw.append(str(v))
    # 常见 Anaconda / 发行版 Python（同事 clone 后若装了 Anaconda 也能自动识别）
    for p in ("C:/ProgramData/Anaconda3/python.exe",
              "C:/Python313/python.exe", "C:/Python312/python.exe"):
        if os.path.exists(p):
            raw.append(p)
    # Windows 自带的 py -3 启动器：解析成真实 exe 路径再加入候选
    raw.append("py -3")

    candidates = []
    for c in raw:
        if " " in c:  # "py -3" → 解析为真实可执行文件路径
            try:
                r = subprocess.run(c.split() + ["-c", "import sys; print(sys.executable)"],
                                   capture_output=True, text=True, timeout=20)
                if r.returncode == 0 and r.stdout.strip():
                    candidates.append(r.stdout.strip())
            except Exception:
                pass
        elif c not in candidates:
            candidates.append(c)

    for c in candidates:
        try:
            r = subprocess.run(
                [c, "-c", "import uvicorn, sqlalchemy, pymysql, fastapi"],
                capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return c
        except Exception:
            pass
    # 全部失败：退回启动器自身 python，并尝试自动安装依赖
    fallback = sys.executable
    sys.stderr.write(
        "\n[启动器] 警告：未找到带 uvicorn/sqlalchemy/pymysql/fastapi 的 Python，"
        "将尝试自动安装依赖到当前 Python 环境。\n"
        "若安装失败，请手动执行：pip install -r backend/requirements.txt\n")
    _auto_install_deps(fallback)
    return fallback


def _auto_install_deps(python: str):
    """自动安装后端依赖（幂等，已装则秒过）。"""
    req_file = BACKEND_DIR / "requirements.txt"
    if not req_file.exists():
        sys.stderr.write(f"[启动器] 未找到 {req_file}，跳过自动安装。\n")
        return
    sys.stderr.write(f"[启动器] 正在为 {python} 安装项目依赖（首次可能需要 1-2 分钟）…\n")
    try:
        r = subprocess.run(
            [python, "-m", "pip", "install", "-r", str(req_file), "-q"],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            sys.stderr.write("[启动器] 依赖安装完成 ✓\n")
        else:
            err_tail = (r.stderr or r.stdout or "").strip()[-300:]
            sys.stderr.write(
                f"[启动器] 依赖安装失败（exit {r.returncode}）：{err_tail}\n"
                f"请手动在终端执行：{python} -m pip install -r {req_file}\n")
    except subprocess.TimeoutExpired:
        sys.stderr.write("[启动器] 依赖安装超时（>5分钟），请检查网络或手动安装。\n")
    except Exception as e:
        sys.stderr.write(f"[启动器] 依赖安装异常：{e}\n")

PYTHON = _resolve_python()
BACKEND_ENV = BACKEND_DIR / ".env"
LOG_FILE = BACKEND_DIR / "launcher_backend.log"

backend_proc = None
backend_lock = threading.Lock()


# ============================ 状态探测 ============================
def check_tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _http_probe(url: str, timeout: float = 3.0) -> tuple[int, str, str]:
    """GET 请求，返回 (状态码, 响应体前 8KB, Content-Type)。连接失败返回 (-1, "", "")。

    与旧的 check_http 不同：4xx/5xx 也带上响应体与类型，便于做内容指纹判断。
    """
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "company-launcher"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            return r.status, r.read(8192).decode("utf-8", "replace"), ctype
    except urllib.error.HTTPError as e:
        try:
            ctype = e.headers.get("Content-Type", "") if e.headers else ""
            return e.code, e.read(8192).decode("utf-8", "replace"), ctype
        except Exception:
            return e.code, "", ""
    except Exception:
        return -1, "", ""


def check_http(url: str, timeout: float = 3.0) -> bool:
    """仅判断能否拿到非 5xx 响应。

    注意：这只说明"该地址有 HTTP 服务"，**不能**用来判断"是不是某个服务"。
    要确认具体服务必须用内容指纹（见 check_dify / check_backend）。
    """
    code, _, _ = _http_probe(url, timeout)
    return 0 <= code < 500


def _env_dify_base() -> str:
    """从 backend/.env 读 DIFY_BASE_URL（支持自定义端口），默认 http://localhost。"""
    try:
        if BACKEND_ENV.exists():
            for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DIFY_BASE_URL="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v.rstrip("/")
    except Exception:
        pass
    return "http://localhost"


def check_backend() -> dict:
    """后端检测：必须命中我们自己的 /api/health，避免 8000 被别的程序占用时误报。"""
    url = f"http://127.0.0.1:{BACKEND_PORT}/api/health"
    if not check_tcp("127.0.0.1", BACKEND_PORT):
        return {"ok": False, "detail": f"未启动（{BACKEND_PORT} 端口未开放）"}
    code, body, _ = _http_probe(url)
    if code == 200 and "ok" in body.lower():
        return {"ok": True, "detail": f"运行中（{BACKEND_PORT}）"}
    if code >= 0:
        return {"ok": False,
                "detail": f"{BACKEND_PORT} 端口有服务，但 /api/health 异常（HTTP {code}）"}
    return {"ok": False, "detail": f"后端无响应（{BACKEND_PORT}）"}


# Dify 内容指纹：每个元素是 (探测路径, 命中条件)
# Dify 内容指纹：仅作为 docker 不可用时的兜底探测
#  - /logo/logo.svg 是 Dify 独有静态资源，返回 Content-Type=image/svg+xml（Steam++ 等不会服务该路径）
#  - /signin /console 的 HTML 含 Next.js 构建标识 turbopack、并引用 /logo/logo.svg
_DIFY_PROBES = (
    ("/logo/logo.svg", lambda code, body, ctype: code == 200 and "svg" in (ctype or "").lower()),
    ("/signin",        lambda code, body, ctype: "turbopack" in body or "/logo/logo.svg" in body),
    ("/console",       lambda code, body, ctype: "turbopack" in body),
)
# Dify docker-compose 的核心服务名（用于 `docker ps` 判定，避免 80 端口争用干扰）
_DIFY_CORE_SERVICES = ("api", "web", "worker", "nginx", "plugin_daemon", "sandbox", "ssrf_proxy")


def _dify_running_via_docker() -> bool | None:
    """通过 docker ps 判断 Dify 容器是否在运行。

    返回 True=在跑, False=没跑, None=无法判断(docker 未安装/守护未启动)。
    当 Steam++ 等程序与 Dify 争用 80 端口时，端口内容指纹会失效，
    而 docker 容器状态是唯一可靠信号，故优先采用。
    """
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=8,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None  # docker 守护未启动等 → 交给端口探测兜底

    running = set()
    for line in r.stdout.splitlines():
        name, _, status = line.partition("\t")
        if "up" not in status.lower():
            continue
        name = name.strip().lower()
        for svc in _DIFY_CORE_SERVICES:
            if svc in name:
                running.add(svc)
    if {"web", "nginx"}.issubset(running):
        return True
    if "web" in running or "nginx" in running:
        return True  # 至少门户/反代在跑，80 能提供 UI
    return False  # 仅有 api/worker 等后台，未对外提供 Web UI


def check_dify() -> dict:
    """Dify 检测：优先用 Docker 容器状态，端口内容指纹作兜底。

    历史 bug：
      1) 曾用 check_tcp(80) → Steam++ 占 80 时误报"运行中"；
      2) 改用 "dify" 字面量 → Dify 是 Next.js SPA，HTML 不含该串，永远判否；
      3) 80 端口上 Dify 与 Steam++ 可同时监听，请求被随机分发，单次探测可能命中 Steam++。
    现改为 Docker 优先：只要 Dify 容器在跑即判定运行中，与 80 端口是否被抢占无关；
    docker 不可用时再回退到端口内容指纹。
    """
    base = _env_dify_base()
    m = re.match(r"https?://([^:/]+)(?::(\d+))?", base)
    host = m.group(1) if m else "127.0.0.1"
    if m and m.group(2):
        port = int(m.group(2))
    else:
        port = 443 if base.startswith("https://") else 80

    # 1) Docker 优先（端口争用时唯一可靠信号）
    docker_state = _dify_running_via_docker()
    if docker_state is True:
        return {"ok": True, "detail": "运行中（Docker 容器已启动）"}
    if docker_state is False:
        return {"ok": False, "detail": "未启动（Docker 中无 Dify 容器在运行）"}

    # 2) docker 不可用时回退到端口内容指纹
    if not check_tcp(host, port):
        return {"ok": False, "detail": f"未检测到服务（{host}:{port} 未开放）"}

    # 每个候选重试 3 次，克服双进程监听导致的请求随机分发
    for path, is_dify in _DIFY_PROBES:
        for _ in range(3):
            code, body, ctype = _http_probe(base + path)
            if code < 0:
                continue
            if is_dify(code, body, ctype):
                return {"ok": True, "detail": f"运行中（{base}{path}）"}

    return {"ok": False,
            "detail": f"{host}:{port} 有服务监听，但响应不是 Dify（可能被其他程序占用）"}


def get_status() -> dict:
    mysql = check_tcp("127.0.0.1", 3306)
    backend = check_backend()
    dify = check_dify()
    return {
        "mysql": mysql,
        "backend": backend["ok"],
        "dify": dify["ok"],
        "detail": {
            "mysql": "运行中（3306）" if mysql else "未启动（3306 端口未开放）",
            "backend": backend["detail"],
            "dify": dify["detail"],
        },
        "ts": datetime.now().strftime("%H:%M:%S"),
    }


# ============================ 数据库一键初始化 ============================
def ensure_db() -> dict:
    """若 backend/.env 已存在，则自动建库建表（幂等）。返回结果 dict。"""
    if not BACKEND_ENV.exists():
        return {"ok": False, "msg": "尚未配置数据库，请先在本页填写 MySQL 信息"}
    try:
        r = subprocess.run(
            [PYTHON, "setup_mysql.py"],
            cwd=str(BACKEND_DIR),
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode == 0:
            return {"ok": True, "msg": "数据库已创建/校验完成（建库 + 8 张表，含 2 张工资表）"}
        err = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        return {"ok": False, "msg": "建库失败：\n" + "\n".join(err)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "建库超时（请确认 MySQL 服务已启动）"}
    except Exception as e:
        return {"ok": False, "msg": f"建库异常：{e}"}


def seed_db() -> dict:
    """执行 contracts/seed.sql 灌入演示数据（幂等，已非空表跳过）。返回结果 dict。"""
    if not BACKEND_ENV.exists():
        return {"ok": False, "msg": "尚未配置数据库，请先在「首次配置」填写 MySQL 信息"}
    try:
        r = subprocess.run(
            [PYTHON, "setup_mysql.py", "--seed-demo"],
            cwd=str(BACKEND_DIR),
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            return {"ok": True, "msg": "演示数据已生成（已存在的表会自动跳过）"}
        err = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
        return {"ok": False, "msg": "生成失败：\n" + "\n".join(err)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "生成超时（数据量较大，请稍后重试）"}
    except Exception as e:
        return {"ok": False, "msg": f"生成异常：{e}"}


def _parse_db_url(url: str) -> dict:
    """mysql+pymysql://user:pwd@host:port/db -> dict。解析失败返回空。"""
    m = re.match(r"^mysql\+pymysql://([^:]+):([^@]*)@([^:/]+):?(\d+)?/(.+)$", url or "")
    if not m:
        return {}
    return {"user": m.group(1), "pwd": m.group(2), "host": m.group(3),
            "port": m.group(4) or "3306", "db": m.group(5)}


def write_env_from_form(form: dict) -> str:
    """根据表单生成 backend/.env（基于 .env.example 模板，替换 DB_URL 与 DIFY_AGENT_KEY）。

    重新配置时：表单为空的项会回退到已有 .env 的对应值，避免把 Dify Key 等项清空。
    """
    host = (form.get("host") or "").strip()
    port = (form.get("port") or "").strip()
    user = (form.get("user") or "").strip()
    pwd = (form.get("pwd") or "").strip()
    db = (form.get("db") or "").strip()
    dify = (form.get("dify") or "").strip()

    # 读取已有 .env，作为回退源
    cur = {}
    if BACKEND_ENV.exists():
        for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
    existing = _parse_db_url(cur.get("DB_URL", ""))

    host = host or existing.get("host") or "127.0.0.1"
    port = port or existing.get("port") or "3306"
    user = user or existing.get("user") or "root"
    pwd = pwd or existing.get("pwd") or ""
    db = db or existing.get("db") or "company_agent"
    dify = dify or cur.get("DIFY_AGENT_KEY", "")
    db_url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"

    tpl_path = ROOT_DIR / ".env.example"
    tpl = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else ""
    out = []
    seen_db = seen_dify = False
    for line in tpl.splitlines():
        if line.startswith("DB_URL="):
            out.append(f"DB_URL={db_url}")
            seen_db = True
        elif line.startswith("DIFY_AGENT_KEY="):
            out.append(f"DIFY_AGENT_KEY={dify}")
            seen_dify = True
        else:
            # 模板里留空的自定义项（如 ROSTER_XLSX=），若已有 .env 有值则沿用
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key and key in cur and cur[key] and line.strip() == key + "=":
                out.append(f"{key}={cur[key]}")
            else:
                out.append(line)
    # 若模板里没有这两个 key（兜底），手动补
    if not seen_db:
        out.append(f"DB_URL={db_url}")
    if not seen_dify:
        out.append(f"DIFY_AGENT_KEY={dify}")
    # 保留模板之外的已有自定义配置（如 ROSTER_XLSX、SEED_ATTENDANCE）
    for k, v in cur.items():
        if k in ("DB_URL", "DIFY_AGENT_KEY"):
            continue
        if not any(l.startswith(k + "=") for l in out):
            out.append(f"{k}={v}")
    BACKEND_ENV.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return db_url


# ============================ 后端启停 ============================
def start_backend() -> dict:
    global backend_proc
    with backend_lock:
        # 若已在运行（无论本启动器起的还是外部起的），不再重复启动
        if check_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health"):
            return {"ok": True, "msg": "后端已在运行", "already": True}
        logf = open(LOG_FILE, "a", encoding="utf-8")
        logf.write(f"\n[{datetime.now()}] === 启动后端 (python={PYTHON}) ===\n")
        logf.flush()
        import time
        try:
            backend_proc = subprocess.Popen(
                [PYTHON, "-m", "uvicorn", "app.main:app",
                 "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
                cwd=BACKEND_DIR,
                stdout=logf,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as e:
            return {"ok": False, "msg": f"启动失败: {e}"}
        # 子进程 3 秒内异常退出 → uvicorn 启动失败（依赖缺失/端口占用等），立即报错而非干等
        for _ in range(6):
            if backend_proc.poll() is not None:
                logf.flush()
                tail = ""
                try:
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        tail = "".join(f.readlines()[-12:])
                except Exception:
                    pass
                return {"ok": False,
                        "msg": "后端启动失败（uvicorn 异常退出）：\n" + tail.strip()[-600:]}
            if check_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health"):
                return {"ok": True, "msg": "后端启动成功", "already": False}
            time.sleep(0.5)
        # 进程还在但端口暂未就绪 → 大概率在加载，先返回，前端会持续刷新状态
        return {"ok": True, "msg": "已发出启动命令，正在初始化（约数秒）…", "already": False}


def stop_backend() -> dict:
    global backend_proc
    with backend_lock:
        stopped = []
        # 1) 停掉本启动器管理的子进程
        if backend_proc is not None and backend_proc.poll() is None:
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=10)
                stopped.append("本启动器子进程")
            except Exception:
                try:
                    backend_proc.kill()
                except Exception:
                    pass
            backend_proc = None
        # 2) 若 8000 仍被占用（外部启动的），按 PID 结束
        if check_tcp("127.0.0.1", BACKEND_PORT):
            import subprocess as _sp
            out = _sp.run(
                ["netstat", "-ano", "|", "findstr", f":{BACKEND_PORT}"],
                capture_output=True, text=True, shell=True,
            ).stdout
            pids = set()
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in line:
                    pids.add(parts[-1])
            for pid in pids:
                try:
                    _sp.run(["taskkill", "/F", "/PID", pid], capture_output=True, shell=True)
                    stopped.append(f"PID {pid}")
                except Exception:
                    pass
        if not stopped:
            return {"ok": True, "msg": "后端未运行，无需停止"}
        return {"ok": True, "msg": f"已停止: {', '.join(stopped)}"}


# ============================ 首次配置向导 HTML ============================
SETUP_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>公司管理智能体 · 首次配置</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: radial-gradient(1200px 600px at 70% -10%, #1b2b4a 0%, #0b1020 55%, #070a14 100%);
    color: #e6ecf5; min-height: 100vh; padding: 36px 18px;
  }
  .wrap { max-width: 560px; margin: 0 auto; }
  h1 { font-size: 22px; font-weight: 700; }
  .sub { color: #8aa0c4; font-size: 13px; margin: 6px 0 22px; }
  .card {
    background: rgba(20,28,48,.72); border: 1px solid rgba(120,150,210,.16);
    border-radius: 16px; padding: 22px; backdrop-filter: blur(8px);
  }
  label { display: block; font-size: 13px; color: #b9c8e6; margin: 14px 0 6px; }
  input {
    width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(120,150,210,.25);
    background: rgba(10,16,32,.6); color: #e6ecf5; font-size: 14px; font-family: inherit;
  }
  input:focus { outline: none; border-color: #4f8cff; }
  .row { display: flex; gap: 12px; }
  .row > div { flex: 1; }
  button {
    margin-top: 22px; width: 100%; cursor: pointer; border: none; border-radius: 10px;
    padding: 12px; font-size: 15px; font-weight: 700; color: #fff;
    background: linear-gradient(135deg,#22c55e,#16a34a); transition: .15s; font-family: inherit;
  }
  button:active { transform: translateY(1px); }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .note { margin-top: 16px; font-size: 12px; color: #7f93b6; line-height: 1.7; }
  .note code { background: rgba(120,150,210,.14); padding: 1px 6px; border-radius: 5px; color: #cfe0ff; }
  .toast {
    position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(20px);
    background: #111a30; border: 1px solid rgba(120,150,210,.25); color: #dfe8f7;
    padding: 10px 18px; border-radius: 12px; font-size: 13px; opacity: 0; transition: .25s;
    pointer-events: none; white-space: pre-line; max-width: 90vw; text-align: center;
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>
<div class="wrap">
  <h1>公司管理智能体 · 数据库配置</h1>
  <div class="sub">请填写你本机 MySQL 信息，启动器将自动建库建表。已配置过也可在此修改密码 / 连接信息。</div>
  <div class="card">
    <form id="f">
      <div class="row">
        <div><label>MySQL 主机</label><input name="host" value="127.0.0.1" required></div>
        <div><label>端口</label><input name="port" value="3306" required></div>
      </div>
      <label>用户名</label><input name="user" value="root" required>
      <label>MySQL 密码</label><input name="pwd" type="password" placeholder="输入 MySQL root 密码" required>
      <label>数据库名</label><input name="db" value="company_agent" required>
      <label>Dify API Key（可选，留空则 AI 问答不可用）</label><input name="dify" placeholder="app-xxxxxxxx">
      <button type="submit" id="btn">保存并初始化数据库</button>
    </form>
    <div class="note">
      前提：你本机已安装并启动了 <code>MySQL 8.0+</code>。没有的话先安装 MySQL 并记住 root 密码。<br>
      提交后启动器会执行 <code>CREATE DATABASE</code> + 建 8 张表（含 2 张工资表），然后回到控制台一键启动前后端。
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(()=>t.classList.remove('show'), 4000);
}
// 页面加载时：若已有 .env，回填当前配置（密码显示为掩码点）
(async ()=>{
  try {
    const r = await fetch('/api/setup-config');
    const d = await r.json();
    if(d.ok && d.host){
      document.querySelector('[name="host"]').value = d.host||'';
      document.querySelector('[name="port"]').value = d.port||'';
      document.querySelector('[name="user"]').value = d.user||'';
      if(d.pwd_masked) document.querySelector('[name="pwd"]').value = d.pwd_masked;
      document.querySelector('[name="db"]').value = d.db||'';
      document.querySelector('[name="dify"]').value = d.dify||'';
      // 密码框获焦时清空掩码，让用户重新输入
      const pwdInput = document.querySelector('[name="pwd"]');
      pwdInput.addEventListener('focus', function(){
        if(this.value === '******') this.value = '';
      });
    }
  }catch(e){/* 首次无 .env 时接口返回 {"ok":false}，静默忽略 */}
})();
document.getElementById('f').onsubmit = async (e)=>{
  e.preventDefault();
  const btn = document.getElementById('btn'); btn.disabled = true; btn.textContent = '正在初始化…';
  const fd = new FormData(e.target);
  // 密码框值为 ******（掩码回填）时，视为未修改，清空让后端用旧值合并
  if(fd.get('pwd') === '******') fd.set('pwd', '');
  const body = new URLSearchParams(fd).toString();
  try{
    const r = await fetch('/api/setup', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
    const d = await r.json();
    if(d.ok){ toast('数据库已就绪，正在进入控制台（若后端已在运行，请先停止再启动使新密码生效）…'); setTimeout(()=>location.href='/', 1400); }
    else { toast(d.msg); btn.disabled = false; btn.textContent = '保存并初始化数据库'; }
  }catch(err){ toast('请求失败: '+err); btn.disabled = false; btn.textContent = '保存并初始化数据库'; }
};
</script>
</body>
</html>"""


# ============================ 仪表盘 HTML ============================
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>公司管理智能体 · 启动器</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: radial-gradient(1200px 600px at 70% -10%, #1b2b4a 0%, #0b1020 55%, #070a14 100%);
    color: #e6ecf5; min-height: 100vh; padding: 36px 18px;
  }
  .wrap { max-width: 880px; margin: 0 auto; }
  .head { display: flex; align-items: center; gap: 14px; margin-bottom: 6px; }
  .head .logo {
    width: 44px; height: 44px; border-radius: 12px;
    background: linear-gradient(135deg,#4f8cff,#7c5cff);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 20px rgba(79,140,255,.35);
  }
  .head h1 { font-size: 22px; font-weight: 700; letter-spacing: .5px; }
  .head .sub { color: #8aa0c4; font-size: 13px; margin-top: 2px; }
  .clock { margin-left: auto; color: #6f86ad; font-size: 13px; font-variant-numeric: tabular-nums; }
  .grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin-top: 24px; }
  @media (max-width: 720px){ .grid { grid-template-columns: 1fr; } }
  .card {
    background: rgba(20,28,48,.72); border: 1px solid rgba(120,150,210,.16);
    border-radius: 16px; padding: 18px; backdrop-filter: blur(8px);
    box-shadow: 0 10px 30px rgba(0,0,0,.25);
  }
  .card .top { display: flex; align-items: center; gap: 10px; }
  .dot { width: 12px; height: 12px; border-radius: 50%; background: #45506b; box-shadow: 0 0 0 0 rgba(0,0,0,0); transition: .3s; }
  .dot.on { background: #34d399; box-shadow: 0 0 12px 2px rgba(52,211,153,.55); }
  .dot.off { background: #f87171; box-shadow: 0 0 12px 2px rgba(248,113,113,.45); }
  .card .name { font-size: 15px; font-weight: 600; }
  .card .meta { color: #7f93b6; font-size: 12px; margin-top: 4px; }
  .card .state { margin-top: 14px; font-size: 13px; font-weight: 600; }
  .card .state.on { color: #34d399; }
  .card .state.off { color: #f87171; }
  .card .why { margin-top: 6px; color: #7f93b6; font-size: 11px; line-height: 1.5; word-break: break-all; min-height: 16px; }
  .card .btns { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
  button {
    cursor: pointer; border: none; border-radius: 10px; padding: 8px 12px;
    font-size: 13px; font-weight: 600; color: #fff; transition: .15s; font-family: inherit;
  }
  button:active { transform: translateY(1px); }
  .b-start { background: linear-gradient(135deg,#22c55e,#16a34a); }
  .b-stop  { background: linear-gradient(135deg,#ef4444,#b91c1c); }
  .b-open  { background: linear-gradient(135deg,#4f8cff,#6366f1); }
  .b-link  { background: rgba(120,150,210,.18); color: #cfe0ff; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  .actions {
    margin-top: 22px; display: flex; gap: 10px; flex-wrap: wrap;
    background: rgba(20,28,48,.55); border:1px solid rgba(120,150,210,.14);
    border-radius: 16px; padding: 16px;
  }
  .actions .label { width: 100%; color: #8aa0c4; font-size: 13px; margin-bottom: 2px; }
  .toast {
    position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(20px);
    background: #111a30; border: 1px solid rgba(120,150,210,.25); color: #dfe8f7;
    padding: 10px 18px; border-radius: 12px; font-size: 13px; opacity: 0;
    transition: .25s; pointer-events: none; box-shadow: 0 10px 30px rgba(0,0,0,.4);
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  .foot { margin-top: 20px; color: #5e7197; font-size: 12px; text-align: center; }
  code { background: rgba(120,150,210,.14); padding: 1px 6px; border-radius: 5px; color: #cfe0ff; }
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="logo">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 5.9L20.5 10l-6.1 2.1L12 18l-2.4-5.9L3.5 10l6.1-2.1z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/></svg>
    </div>
    <div>
      <h1>公司管理智能体</h1>
      <div class="sub">服务启动器 · 一键管理后端与前端</div>
    </div>
    <div class="clock" id="clock">--:--:--</div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="top"><span class="dot" id="dot-mysql"></span><span class="name">MySQL 数据库</span></div>
      <div class="meta">端口 3306 · 由系统服务管理</div>
      <div class="state" id="state-mysql">检测中…</div>
      <div class="why" id="why-mysql"></div>
      <div class="btns"><button class="b-link" disabled>只读监控</button></div>
    </div>

    <div class="card">
      <div class="top"><span class="dot" id="dot-backend"></span><span class="name">后端 FastAPI</span></div>
      <div class="meta">端口 8000 · 可一键启停</div>
      <div class="state" id="state-backend">检测中…</div>
      <div class="why" id="why-backend"></div>
      <div class="btns">
        <button class="b-start" id="btn-start">启动</button>
        <button class="b-stop" id="btn-stop">停止</button>
      </div>
    </div>

    <div class="card">
      <div class="top"><span class="dot" id="dot-dify"></span><span class="name">Dify 平台</span></div>
      <div class="meta">端口 80 · Docker 管理</div>
      <div class="state" id="state-dify">检测中…</div>
      <div class="why" id="why-dify"></div>
      <div class="btns"><button class="b-open" id="btn-dify">打开控制台</button></div>
    </div>
  </div>

  <div class="actions">
    <div class="label">快捷入口</div>
    <button class="b-open" id="btn-fe">打开前端页面</button>
    <button class="b-link" id="btn-docs">后端 API 文档</button>
    <button class="b-link" id="btn-seed">生成演示数据</button>
    <button class="b-link" id="btn-setup">配置数据库</button>
    <button class="b-link" id="btn-refresh">立即刷新状态</button>
  </div>

  <div class="foot">启动器端口 <code>9000</code> · 后端日志 <code>backend/launcher_backend.log</code></div>
</div>

<div class="toast" id="toast"></div>

<script>
const DASH = `http://${location.hostname}:9000`;
function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(()=>t.classList.remove('show'), 2600);
}
function setCard(key, on, detail){
  document.getElementById('dot-'+key).className = 'dot ' + (on?'on':'off');
  const s = document.getElementById('state-'+key);
  s.className = 'state ' + (on?'on':'off');
  s.textContent = on ? '● 运行中' : '○ 已停止';
  const w = document.getElementById('why-'+key);
  if(w) w.textContent = detail || '';
}
async function refresh(){
  try{
    const r = await fetch('/api/status'); const d = await r.json();
    const dt = d.detail || {};
    setCard('mysql', d.mysql, dt.mysql);
    setCard('backend', d.backend, dt.backend);
    setCard('dify', d.dify, dt.dify);
    document.getElementById('clock').textContent = '更新于 ' + d.ts;
  }catch(e){ toast('状态获取失败: '+e); }
}
document.getElementById('btn-start').onclick = async ()=>{
  document.getElementById('btn-start').disabled = true; toast('正在启动后端…');
  const r = await fetch('/api/start',{method:'POST'}); const d = await r.json();
  toast(d.msg); document.getElementById('btn-start').disabled = false; refresh();
};
document.getElementById('btn-stop').onclick = async ()=>{
  const r = await fetch('/api/stop',{method:'POST'}); const d = await r.json();
  toast(d.msg); refresh();
};
document.getElementById('btn-dify').onclick = ()=> window.open('http://localhost/console','_blank');
document.getElementById('btn-fe').onclick = ()=> window.open(DASH + '/fe/index.html','_blank');
document.getElementById('btn-docs').onclick = ()=> window.open('http://localhost:8000/docs','_blank');
document.getElementById('btn-seed').onclick = async ()=>{
  toast('正在生成演示数据…');
  try{
    const r = await fetch('/api/seed',{method:'POST'}); const d = await r.json();
    toast(d.msg);
  }catch(e){ toast('生成失败: '+e); }
  refresh();
};
document.getElementById('btn-refresh').onclick = refresh;
document.getElementById('btn-setup').onclick = ()=> location.href = '/setup';

refresh(); setInterval(refresh, 3000);
</script>
</body>
</html>"""


# ============================ HTTP 服务 ============================
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # 静默访问日志

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, fpath):
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            ext = os.path.splitext(fpath)[1].lower()
            self._send(200, data, MIME.get(ext, "application/octet-stream"))
        except Exception:
            self._send(404, "Not Found")

    # ---- 反向代理：把 /api/* 转发到后端 8000（前端通过 9000 访问时 API 不再 404）----
    def _proxy(self, method="GET"):
        """将请求原样转发到 http://127.0.0.1:8000，返回后端的完整响应。"""
        target = f"http://127.0.0.1:{BACKEND_PORT}{self.path}"
        try:
            # 读 body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            # 构造转发请求头（去掉 hop-by-hop 头）
            fwd_headers = {}
            for k, v in self.headers.items():
                kl = k.lower()
                if kl in ("host", "connection", "transfer-encoding", "content-length"):
                    if kl == "content-length" and body:
                        fwd_headers[k] = str(len(body))
                    continue
                fwd_headers[k] = v
            fwd_headers["Host"] = f"127.0.0.1:{BACKEND_PORT}"
            req = urllib.request.Request(target, data=body, headers=fwd_headers, method=method)
            with urllib.request.urlopen(req, timeout=120) as resp:  # Dify Agent+工具调用可能需 30~60s，留足余量
                status = resp.status
                resp_body = resp.read()
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(resp_body)))
            # 转发 CORS 头（让前端能读到）
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read() if e.fp else b""
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(err_body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            self._send(502, json.dumps({"error": f"后端不可用: {e}"}, ensure_ascii=False))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            # 尚未配置数据库 → 首次配置向导；否则显示控制台
            if not BACKEND_ENV.exists():
                self._send(200, SETUP_HTML, "text/html; charset=utf-8")
            else:
                self._send(200, DASHBOARD_HTML, "text/html; charset=utf-8")
        elif path == "/setup":
            # 常驻配置页：无论是否已配置，都可直接访问（用于首次配置或修改密码）
            self._send(200, SETUP_HTML, "text/html; charset=utf-8")
        elif path == "/api/setup-config":
            # 返回当前 .env 配置（密码脱敏为 ******），供 /setup 页面回填表单
            if BACKEND_ENV.exists():
                cur = _parse_db_url("")
                existing = {}
                for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()
                db_info = _parse_db_url(existing.get("DB_URL", ""))
                self._send(200, json.dumps({
                    "ok": True,
                    "host": db_info.get("host", ""),
                    "port": db_info.get("port", ""),
                    "user": db_info.get("user", ""),
                    "pwd_masked": "******" if db_info.get("pwd") else "",
                    "db": db_info.get("db", ""),
                    "dify": existing.get("DIFY_AGENT_KEY", ""),
                }, ensure_ascii=False))
            else:
                self._send(200, json.dumps({"ok": False}, ensure_ascii=False))
        elif path == "/api/status":
            self._send(200, json.dumps(get_status(), ensure_ascii=False))
        elif path.startswith("/fe/"):
            rel = path[len("/fe/"):]
            if not rel:
                rel = "index.html"
            fpath = os.path.normpath(os.path.join(FRONTEND_DIR, rel))
            # 防止目录穿越
            if not fpath.startswith(os.path.abspath(FRONTEND_DIR)):
                self._send(403, "Forbidden")
                return
            if os.path.isfile(fpath):
                self._send_file(fpath)
            else:
                self._send(404, "Not Found")
        elif path.startswith("/api/"):
            # 反向代理到后端 8000（前端通过 9000 访问时 API 不再 404）
            self._proxy("GET")
        else:
            self._send(404, "Not Found")

    def _handle_setup(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
            write_env_from_form(form)
            res = ensure_db()
            self._send(200, json.dumps(res, ensure_ascii=False))
        except Exception as e:
            self._send(200, json.dumps(
                {"ok": False, "msg": f"配置写入失败：{e}"}, ensure_ascii=False))

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/setup":
            self._handle_setup()
        elif path == "/api/start":
            # 不再在此同步建库（避免阻塞用户点击）。建库在启动器启动时后台跑过一次，
            # 正常 clone 后首次配置向导也会建库。这里只负责拉起后端。
            self._send(200, json.dumps(start_backend(), ensure_ascii=False))
        elif path == "/api/stop":
            self._send(200, json.dumps(stop_backend(), ensure_ascii=False))
        elif path == "/api/seed":
            self._send(200, json.dumps(seed_db(), ensure_ascii=False))
        elif path.startswith("/api/"):
            # 反向代理到后端 8000
            self._proxy("POST")
        else:
            self._send(404, "Not Found")

    def do_PUT(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._proxy("PUT")
        else:
            self._send(404, "Not Found")

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._proxy("DELETE")
        else:
            self._send(404, "Not Found")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    # 后台校验/初始化数据库一次（幂等，不阻塞仪表盘）。DB 已存在则秒过。
    threading.Thread(target=lambda: ensure_db(), daemon=True).start()
    httpd = Server(("0.0.0.0", DASHBOARD_PORT), Handler)
    url = f"http://localhost:{DASHBOARD_PORT}/"
    print(f"[启动器] 仪表盘已启动: {url}")
    print(f"[启动器] 前端页面: http://localhost:{DASHBOARD_PORT}/fe/index.html")
    print(f"[启动器] 按 Ctrl+C 退出（退出不会停止后端）")
    def _open():
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[启动器] 已退出")
        httpd.server_close()


if __name__ == "__main__":
    main()
