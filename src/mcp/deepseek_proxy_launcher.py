#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Proxy 启动器 - 从 TS2 系统内部启动 DeepSeek 网页版反代服务
将 DeepSeek 网页版免费额度变成 OpenAI 兼容的本地 API 服务

启动方式：
  python -m mcp.deepseek_proxy_launcher
  python -m mcp.deepseek_proxy_launcher --token YOUR_BEARER_TOKEN
  python -m mcp.deepseek_proxy_launcher --password your@email.com --ask-pass
  python -m mcp.deepseek_proxy_launcher --help
"""

import sys
import os
import argparse
import asyncio
import threading
import subprocess
import time
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Proxy 项目路径
PROXY_DIR = Path(__file__).parent.parent.parent / "TS2-reference" / "proxy" / "WebChat2Api-master" / "src"


def check_proxy_dependencies() -> bool:
    """检查 DeepSeek Proxy 依赖是否已安装"""
    required = ["fastapi", "uvicorn", "httpx", "wasmtime"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"❌ 缺少依赖: {', '.join(missing)}")
        print(f"   安装命令: pip install {' '.join(missing)}")
        return False
    return True


def get_saved_token() -> Optional[str]:
    """从本地配置读取保存的 Token"""
    config_path = Path.home() / ".ts2" / "deepseek_proxy_token.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("token")
        except Exception:
            pass
    return None


def save_token(token: str):
    """保存 Token 到本地配置"""
    config_dir = Path.home() / ".ts2"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "deepseek_proxy_token.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f, indent=2)
        print(f"✅ Token 已保存到: {config_path}")
    except Exception as e:
        print(f"⚠️ 保存 Token 失败: {e}")


def start_proxy_server(
    token: str,
    host: str = "127.0.0.1",
    port: int = 5317,
    session_mode: str = "reuse",
    headless: bool = True,
) -> Optional[subprocess.Popen]:
    """
    启动 DeepSeek Proxy 服务
    
    参数:
        token: DeepSeek Bearer Token
        host: 监听地址
        port: 监听端口
        session_mode: 会话模式 (reuse 或 new)
        headless: 是否静默运行
    
    返回:
        subprocess.Popen 对象，或 None（启动失败）
    """
    if not PROXY_DIR.exists():
        print(f"❌ Proxy 项目不存在: {PROXY_DIR}")
        return None
    
    env = os.environ.copy()
    env["DEEPSEEK_AUTH_MODE"] = "token"
    env["DEEPSEEK_BEARER_TOKEN"] = token
    env["DEEPSEEK_SESSION_MODE"] = session_mode
    env["DEEPSEEK_HOST"] = host
    env["DEEPSEEK_PORT"] = str(port)
    
    python_path = sys.executable
    
    cmd = [python_path, "-m", "deepseek_proxy.main"]
    
    print(f"🚀 启动 DeepSeek Proxy: {host}:{port}")
    print(f"   认证模式: token")
    print(f"   会话模式: {session_mode}")
    print(f"   Proxy 目录: {PROXY_DIR}")
    
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROXY_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return process
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return None


def wait_for_server(host: str, port: int, timeout: int = 30) -> bool:
    """等待服务器启动"""
    import urllib.request
    
    start_time = time.time()
    url = f"http://{host}:{port}/health"
    
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.urlopen(url, timeout=3)
            if req.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    
    return False


def monitor_output(process: subprocess.Popen):
    """在后台线程监控 Proxy 输出"""
    try:
        if process.stdout:
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    # 转发到日志
                    logger.info(f"[DeepSeekProxy] {line}")
                    # 也打印到控制台
                    print(f"[Proxy] {line}")
    except Exception as e:
        logger.error(f"Proxy 输出监控异常: {e}")


def start_proxy_in_background(token: str, host: str = "127.0.0.1", port: int = 5317) -> Optional[subprocess.Popen]:
    """
    在后台启动 DeepSeek Proxy
    
    返回:
        subprocess.Popen 对象，可用于后续停止
    """
    if not check_proxy_dependencies():
        return None
    
    # 先检查是否已有服务在运行
    try:
        if wait_for_server(host, port, timeout=2):
            print(f"✅ DeepSeek Proxy 已在运行: {host}:{port}")
            print(f"   测试: curl http://{host}:{port}/v1/models")
            return None  # 已经在运行
    except Exception:
        pass
    
    process = start_proxy_server(token, host, port)
    if process is None:
        return None
    
    # 启动输出监控线程
    monitor_thread = threading.Thread(target=monitor_output, args=(process,), daemon=True)
    monitor_thread.start()
    
    # 等待服务就绪
    print(f"⏳ 等待 Proxy 启动...")
    if wait_for_server(host, port, timeout=15):
        print(f"✅ DeepSeek Proxy 已就绪: http://{host}:{port}")
        print(f"   API 端点: http://{host}:{port}/v1/chat/completions")
        print(f"   模型列表: http://{host}:{port}/v1/models")
        print(f"   健康检查: http://{host}:{port}/health")
        print(f"\n📌 TS2 配置指南:")
        print(f"   Provider: DeepSeek Proxy (本地反代)")
        print(f"   Base URL: http://{host}:{port}/v1")
        print(f"   API Key: any (任意值)")
        print(f"   Model: deepseek-v4-flash 或 deepseek-v4")
    else:
        print(f"❌ Proxy 启动超时，请检查 Token 是否有效")
        process.kill()
        return None
    
    return process


def stop_proxy(process: subprocess.Popen):
    """停止 DeepSeek Proxy"""
    if process:
        try:
            process.kill()
            process.wait(timeout=5)
            print("✅ DeepSeek Proxy 已停止")
        except Exception as e:
            print(f"⚠️ 停止失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="DeepSeek Proxy 启动器")
    parser.add_argument("--token", type=str, help="DeepSeek Bearer Token")
    parser.add_argument("--password", type=str, help="DeepSeek 账号邮箱")
    parser.add_argument("--ask-pass", action="store_true", help="交互式输入密码")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=5317, help="监听端口")
    parser.add_argument("--mode", type=str, default="reuse", choices=["reuse", "new"], help="会话模式")
    
    args = parser.parse_args()
    
    # 获取 Token
    token = args.token
    if not token:
        # 尝试从本地配置读取
        token = get_saved_token()
        if token:
            print(f"✅ 使用已保存的 Token")
        else:
            print("❌ 未提供 Token，也未找到已保存的 Token")
            print(f"   获取方式: 浏览器打开 chat.deepseek.com → F12 → Network → 找 Authorization: Bearer xxx")
            print(f"   或使用: python -m mcp.deepseek_proxy_launcher --token YOUR_TOKEN")
            sys.exit(1)
    
    # 启动
    process = start_proxy_in_background(token, args.host, args.port)
    if process:
        # 保存 Token
        save_token(token)
        
        try:
            # 保持运行，直到用户 Ctrl+C
            print(f"\n按 Ctrl+C 停止 Proxy...")
            process.wait()
        except KeyboardInterrupt:
            print(f"\n🛑 收到停止信号...")
            stop_proxy(process)


if __name__ == "__main__":
    main()
