# -*- coding: utf-8 -*-
"""
公司管理智能体 · 一键关闭器
-------------------------------------------------
双击同级目录的 stopper.bat 即可停止所有本地服务：
  - FastAPI 后端（端口 8000）
  - 启动器仪表盘（端口 9000）

纯标准库实现，无需额外依赖；仅 Windows 平台（与启动器同栈）。
"""
import subprocess
import sys
import time

# 要停止的本地服务端口：后端 8000 + 启动器仪表盘 9000
PORTS = (8000, 9000)


def pids_on_port(port: int) -> set:
    """返回正在 LISTEN 指定端口的进程 PID 集合（精确匹配端口号）。"""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=20)
        # 中文 Windows 下 netstat 输出为 GBK，直接 utf-8 解码会崩；
        # 端口/PID 均为 ASCII，用 errors="replace" 丢弃非 ASCII 即可。
        text = (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return set()
    pids = set()
    for line in text.splitlines():
        parts = line.split()
        # 典型行：TCP    0.0.0.0:8000    0.0.0.0:0    LISTENING    12345
        if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTENING" in parts:
            local = parts[1]  # 本地地址，如 0.0.0.0:8000 或 [::]:8000
            if local.endswith(f":{port}"):
                pids.add(parts[-1])
    return pids


def kill_pid(pid: str) -> bool:
    try:
        r = subprocess.run(
            ["taskkill", "/F", "/PID", pid], capture_output=True, timeout=15
        )
        return r.returncode == 0
    except Exception:
        return False


def main() -> None:
    print("=== 公司管理智能体 · 一键关闭 ===")
    killed = []
    for port in PORTS:
        pids = pids_on_port(port)
        if not pids:
            print(f"[端口 {port}] 未发现运行中的服务（无需停止）")
            continue
        for pid in sorted(pids):
            if kill_pid(pid):
                killed.append((port, pid))
                print(f"[端口 {port}] 已停止进程 PID {pid}")
            else:
                print(f"[端口 {port}] 停止 PID {pid} 失败（可能需要管理员权限）")

    # 给系统一点时间释放端口
    time.sleep(1.0)

    # 校验：是否还有残留
    still = {p: pids_on_port(p) for p in PORTS if pids_on_port(p)}
    if still:
        for p, ps in still.items():
            print(f"[警告] 端口 {p} 仍有进程未退出：{', '.join(sorted(ps))}")
        print("提示：可重试一次，或以管理员身份运行关闭器。")
    else:
        print("所有本地服务已停止，端口已释放。")

    if not killed:
        print("（本次没有需要关闭的服务）")
    print()
    input("按 Enter 退出...")


if __name__ == "__main__":
    main()
