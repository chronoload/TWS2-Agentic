#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rano_app_dbg - 多服务调试启动器（用户 / 机器双通道）

并发启动 TS2 主服务，统一日志落盘 + 健康检查 + 优雅停止。

用法：
  # 用户：交互式启动（Ctrl+C 优雅停止）
  python rano_app_dbg.py
  # 用户：不开浏览器
  python rano_app_dbg.py --no-browser
  # 机器（Agent/自动化）：启动并返回结构化 JSON（--json 抑制日志面板）
  python rano_app_dbg.py --json
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 服务定义：name -> {desc, kind: thread|subprocess, run 参数}
# thread 服务：callable(*args, **kwargs) 启动，返回 (handle, port)
SERVICES = {
    "ts2": {
        "desc": "TS2 主服务（自动分配端口）",
        "kind": "thread",
        "module": "mcp.server.app",
        "func": "run_server_in_thread",
    },
}


# ─── 服务启动器 ───────────────────────────────────────────────
def _start_ts2(host: str, no_browser: bool, log_fh):
    """线程启动 TS2 主服务（auto_port 自动分配端口），返回 (handle, actual_port)"""
    import importlib
    mod = importlib.import_module(SERVICES["ts2"]["module"])
    fn = getattr(mod, SERVICES["ts2"]["func"])
    server, thread, actual_port = fn(
        workspace_dir=str(ROOT),
        host=host,
        port=6906,
        open_browser=not no_browser,
        auto_port=True,
    )
    return {"server": server, "thread": thread}, actual_port


_STARTERS = {"ts2": _start_ts2}


# ─── 健康检查 ─────────────────────────────────────────────────
def _http_ok(host: str, port: int, timeout: float = 1.0) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout):
            return True
    except Exception:
        return False


def _check(service: str, handle, port: int, host: str) -> dict:
    """探活一次，返回 {status, port}"""
    st = {"status": "up", "port": port}
    try:
        srv = handle.get("server")
        if srv is not None:
            if getattr(srv, "should_exit", False):
                st["status"] = "stopped"
            elif not _http_ok(host, port):
                st["status"] = "starting"
    except Exception:
        st["status"] = "error"
    return st


# ─── 主流程 ───────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rano_app_dbg",
        description="TS2 调试启动器（用户 / 机器双通道）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--no-browser", action="store_true", help="TS2 不自动打开浏览器")
    ap.add_argument("--host", type=str, default="0.0.0.0", help="TS2 监听地址")
    ap.add_argument("--json", action="store_true",
                    help="机器模式：输出结构化 JSON（含服务状态）")
    args = ap.parse_args(argv)

    names = ["ts2"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    handles = {}
    logs = {}

    for name in names:
        log_path = LOG_DIR / f"rano_{name}_{ts}.log"
        fh = open(log_path, "a", encoding="utf-8", buffering=1)
        logs[name] = str(log_path)
        try:
            handle, port = _STARTERS[name](args.host, args.no_browser, fh)
            handles[name] = {"handle": handle, "port": port, "log": fh}
            if not args.json:
                print(f"🚀 [{name}] 启动中... port={port}  log={log_path}", flush=True)
        except Exception as e:
            if not args.json:
                print(f"❌ [{name}] 启动失败: {e}", file=sys.stderr, flush=True)
            else:
                handles[name] = {"error": str(e), "log": str(log_path)}

    if args.json:
        # 机器模式：等待就绪（最多 15s），输出一次结构化状态后返回
        statuses = {}
        deadline = time.time() + 15
        while time.time() < deadline and any(
            "error" not in v for v in handles.values() if isinstance(v, dict)
        ):
            done = True
            for name, info in handles.items():
                if "error" in info:
                    statuses[name] = {"status": "error", "error": info["error"],
                                      "port": None, "log": logs.get(name)}
                    continue
                st = _check(name, info["handle"], info["port"], args.host)
                statuses[name] = {"status": st["status"], "port": st["port"],
                                  "log": logs.get(name)}
                if st["status"] in ("starting",):
                    done = False
            if done:
                break
            time.sleep(1)
        print(json.dumps({"started": list(names), "status": statuses},
                         ensure_ascii=False, indent=2))
        for info in handles.values():
            if "log" in info:
                try:
                    info["log"].close()
                except Exception:
                    pass
        return 0

    # 用户模式：状态面板循环，Ctrl+C 优雅停止
    print("\n── 服务状态（Ctrl+C 停止全部）──", flush=True)
    try:
        while True:
            lines = []
            for name, info in handles.items():
                if "error" in info:
                    lines.append(f"  [{name}] ❌ {info['error']}")
                    continue
                st = _check(name, info["handle"], info["port"], args.host)
                icon = {"up": "✅", "starting": "⏳", "stopped": "⏹", "error": "❌"}.get(st["status"], "❓")
                lines.append(f"  {icon} [{name}] {st['status']:<9} port={st['port']}")
            print("\033[2J\033[H" + "\n".join(lines), flush=True)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n⏹ 正在停止全部服务...", flush=True)
        _stop_all(handles)
        print("✅ 已全部停止", flush=True)
    return 0


def _stop_all(handles):
    """优雅停止：TS2 置 should_exit"""
    for name, info in handles.items():
        if "error" in info:
            continue
        try:
            srv = info["handle"].get("server")
            if srv is not None:
                srv.should_exit = True
        except Exception as e:
            print(f"  ⚠️ [{name}] 停止异常: {e}", file=sys.stderr)
        finally:
            try:
                info["log"].close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
