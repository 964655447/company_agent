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
from datetime import datetime

# ============================ 配置 ============================
BACKEND_PORT = 8000
DASHBOARD_PORT = 9000
PYTHON = r"***REMOVED***"
BACKEND_DIR = r"***REMOVED***\backend"
FRONTEND_DIR = r"***REMOVED***\frontend"
LOG_FILE = os.path.join(BACKEND_DIR, "launcher_backend.log")

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


def check_http(url: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def get_status() -> dict:
    mysql = check_tcp("127.0.0.1", 3306)
    backend = check_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
    dify = check_tcp("127.0.0.1", 80) or check_http("http://localhost/")
    return {
        "mysql": mysql,
        "backend": backend,
        "dify": dify,
        "ts": datetime.now().strftime("%H:%M:%S"),
    }


# ============================ 后端启停 ============================
def start_backend() -> dict:
    global backend_proc
    with backend_lock:
        # 若已在运行（无论本启动器起的还是外部起的），不再重复启动
        if check_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health"):
            return {"ok": True, "msg": "后端已在运行", "already": True}
        logf = open(LOG_FILE, "a", encoding="utf-8")
        logf.write(f"\n[{datetime.now()}] === 启动后端 ===\n")
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
        # 最多等 15 秒确认起来
        for _ in range(30):
            if check_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health"):
                return {"ok": True, "msg": "后端启动成功", "already": False}
            import time
            time.sleep(0.5)
        return {"ok": True, "msg": "已发出启动命令，仍在初始化…", "already": False}


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
      <div class="btns"><button class="b-link" disabled>只读监控</button></div>
    </div>

    <div class="card">
      <div class="top"><span class="dot" id="dot-backend"></span><span class="name">后端 FastAPI</span></div>
      <div class="meta">端口 8000 · 可一键启停</div>
      <div class="state" id="state-backend">检测中…</div>
      <div class="btns">
        <button class="b-start" id="btn-start">启动</button>
        <button class="b-stop" id="btn-stop">停止</button>
      </div>
    </div>

    <div class="card">
      <div class="top"><span class="dot" id="dot-dify"></span><span class="name">Dify 平台</span></div>
      <div class="meta">端口 80 · Docker 管理</div>
      <div class="state" id="state-dify">检测中…</div>
      <div class="btns"><button class="b-open" id="btn-dify">打开控制台</button></div>
    </div>
  </div>

  <div class="actions">
    <div class="label">快捷入口</div>
    <button class="b-open" id="btn-fe">打开前端页面</button>
    <button class="b-link" id="btn-docs">后端 API 文档</button>
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
function setCard(key, on){
  document.getElementById('dot-'+key).className = 'dot ' + (on?'on':'off');
  const s = document.getElementById('state-'+key);
  s.className = 'state ' + (on?'on':'off');
  s.textContent = on ? '● 运行中' : '○ 已停止';
}
async function refresh(){
  try{
    const r = await fetch('/api/status'); const d = await r.json();
    setCard('mysql', d.mysql); setCard('backend', d.backend); setCard('dify', d.dify);
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
document.getElementById('btn-refresh').onclick = refresh;

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
            with urllib.request.urlopen(req, timeout=30) as resp:
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
            self._send(200, DASHBOARD_HTML, "text/html; charset=utf-8")
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

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/start":
            self._send(200, json.dumps(start_backend(), ensure_ascii=False))
        elif path == "/api/stop":
            self._send(200, json.dumps(stop_backend(), ensure_ascii=False))
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
