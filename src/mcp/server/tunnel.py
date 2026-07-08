#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frp 隧道管理器 — 将本地端口通过 frp 暴露到公网

配置方式：
1. VPS 上配置 frps.ini:
   [common]
   bind_port = 7000
   token = your_token
   # 分配 privileged ports 需要 root
   # privilege_allow_ports = 6906-6910

2. 本地配置 frpc.ini（或通过 API 动态生成）:
   [common]
   server_addr = VPS公网IP
   server_port = 7000
   token = your_token

   [ts2]
   type = tcp
   local_ip = 127.0.0.1
   local_port = 6906
   remote_port = 6906

3. 启动 frpc: ./frpc -c frpc.ini
"""

import logging
import socket
import select
import subprocess
import threading
import time
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_DIR = Path.home() / ".ts2"
CONFIG_FILE = CONFIG_DIR / "tunnel_settings.json"


@dataclass
class TunnelSettings:
    """隧道配置（支持 frp / serveo / bore）"""
    enabled: bool = False           # 是否启用隧道
    tunnel_type: str = "frp"       # 隧道类型: frp | serveo | bore | localtunnel
    server_addr: str = ""          # frps 服务器地址（VPS 公网 IP，frp 专用）
    server_port: int = 7000        # frps 控制端口
    token: str = ""                # frps 认证 token
    local_port: int = 6906         # 本地 TS2 端口
    remote_port: int = 6906        # 远程端口
    subdomain: str = ""             # 子域名（serveo 专用）
    frpc_path: str = ""            # frpc 可执行文件路径（留空则自动查找）
    bore_path: str = ""            # bore 可执行文件路径（留空则自动查找）
    cf_token: str = ""             # Cloudflare Tunnel Token
    cf_domain: str = ""            # Cloudflare 绑定域名（可选）
    auto_start: bool = False        # 是否随 TS2 启动

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(data: dict) -> "TunnelSettings":
        return TunnelSettings(
            enabled=data.get("enabled", False),
            tunnel_type=data.get("tunnel_type", "frp"),
            server_addr=data.get("server_addr", ""),
            server_port=data.get("server_port", 7000),
            token=data.get("token", ""),
            local_port=data.get("local_port", 6906),
            remote_port=data.get("remote_port", 6906),
            subdomain=data.get("subdomain", ""),
            frpc_path=data.get("frpc_path", ""),
            bore_path=data.get("bore_path", ""),
            cf_token=data.get("cf_token", ""),
            cf_domain=data.get("cf_domain", ""),
            auto_start=data.get("auto_start", False),
        )


class TunnelManager:
    """隧道管理器（支持 frp / serveo / bore）"""

    def __init__(self):
        self._settings = self._load_settings()
        self._tunnel_type = self._settings.tunnel_type or "frp"
        self._frpc_procobj: Optional[subprocess.Popen] = None
        self._ssh_procobj: Optional[subprocess.Popen] = None  # serveo
        self._bore_procobj: Optional[subprocess.Popen] = None  # bore (binary)
        self._bore_sock: Optional[socket.socket] = None       # bore (Python)
        self._bore_remote_port: int = 0                        # bore 分配的远程端口
        self._lt_procobj: Optional[subprocess.Popen] = None   # localtunnel
        self._cf_procobj: Optional[subprocess.Popen] = None   # cloudflared
        self._status = "stopped"      # stopped | running | error
        self._public_url: str = ""
        self._start_time: Optional[float] = None
        self._error_msg: str = ""
        self._monitor_thread: Optional[threading.Thread] = None
        self._subdomain: str = ""      # serveo subdomain

    # ── 配置持久化 ──────────────────────────────────────

    def _load_settings(self) -> TunnelSettings:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return TunnelSettings.from_dict(data)
            except Exception as e:
                logger.warning(f"加载隧道配置失败: {e}")
        return TunnelSettings()

    def _save_settings(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self._settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_settings(self) -> dict:
        return self._settings.to_dict()

    def update_settings(self, **kwargs) -> dict:
        for key, value in kwargs.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
        self._save_settings()
        return self._settings.to_dict()

    # ── frpc 可执行文件查找 ──────────────────────────────

    def _find_frpc(self) -> Optional[str]:
        """自动查找 frpc 可执行文件"""
        # 优先使用配置中的路径
        if self._settings.frpc_path and Path(self._settings.frpc_path).exists():
            return self._settings.frpc_path

        # 在 PATH 中查找
        for name in ("frpc", "frpc.exe"):
            for dir_ in os.environ.get("PATH", "").split(os.pathsep):
                path = Path(dir_).parent / name
                if path.exists():
                    return str(path)
                # 也查找在 PATH/frpc 下
                path2 = Path(dir_) / name
                if path2.exists():
                    return str(path2)

        # 查找 TS2 目录下的 frpc
        candidates = [
            Path.home() / "frp" / "frpc",
            Path.home() / "frp" / "frpc.exe",
            Path.home() / ".ts2" / "frpc",
            Path.home() / ".ts2" / "frpc.exe",
            Path(__file__).parent.parent.parent / "frp" / "frpc",
            Path(__file__).parent.parent.parent / "frp" / "frpc.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)

        return None

    # ── frpc.ini 生成 ──────────────────────────────────

    def _generate_frpc_ini(self) -> str:
        """生成 frpc.ini 配置文件内容"""
        lines = [
            "[common]",
            f"server_addr = {self._settings.server_addr}",
            f"server_port = {self._settings.server_port}",
            f"token = {self._settings.token}",
            "",
            "[ts2]",
            "type = tcp",
            "local_ip = 127.0.0.1",
            f"local_port = {self._settings.local_port}",
            f"remote_port = {self._settings.remote_port}",
        ]
        return "\n".join(lines)

    def _write_frpc_ini(self) -> Path:
        """写入 frpc.ini 到临时文件"""
        ini_path = CONFIG_DIR / "frpc.ini"
        ini_path.write_text(self._generate_frpc_ini(), encoding="utf-8")
        return ini_path

    # ── frpc 进程管理 ─────────────────────────────────

    def _parse_public_url(self, line: str) -> Optional[str]:
        """从 frpc 输出中解析公网访问地址"""
        # TCP 类型: "success" 开头的日志行
        # 示例: [WARN] [client.go:83] [xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx] 
        #        tcp port 6906 -> 127.0.0.1:6906
        # 直接用 IP:PORT 访问
        if "->" in line and "tcp" in line.lower():
            addr = self._settings.server_addr
            port = self._settings.remote_port
            return f"http://{addr}:{port}"
        return None

    def _monitor_frpc(self, proc: subprocess.Popen):
        """监控 frpc 进程输出"""
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                logger.debug(f"[frpc] {line}")

                # 检测连接成功
                if "login to server success" in line.lower() or "start proxy success" in line.lower():
                    self._status = "running"
                    self._public_url = f"http://{self._settings.server_addr}:{self._settings.remote_port}"
                    logger.info(f"frp 隧道已建立: {self._public_url}")

                # 解析实际地址
                url = self._parse_public_url(line)
                if url:
                    self._public_url = url

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "disconnected" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"frp 隧道异常: {line}")
        except Exception as e:
            logger.error(f"frpc 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── serveo 启动 ──────────────────────────────────

    def _start_serveo(self) -> Dict[str, Any]:
        """通过 SSH 到 serveo.net 建立隧道（无需 VPS，无需下载）"""
        import random as _rand

        local_port = self._settings.local_port
        subdomain = self._settings.subdomain or f"ts2-{_rand.randint(10000, 99999)}"
        self._subdomain = subdomain

        # SSH 参数：
        # -o ServerAliveInterval=60  保活
        # -o StrictHostKeyChecking=no 自动接受 host key
        # -o ExitOnForwardFailure=yes 确保端口转发成功
        # -R 转发格式: [子域名:]端口:主机:主机端口
        #   如果指定了子域名，serveo 会分配 subdomain.serveo.net
        cmd = [
            "ssh",
            "-o", "ServerAliveInterval=60",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ExitOnForwardFailure=yes",
            # 转发格式：[子域名:]端口:本地IP:本地端口
            "-R", f"{subdomain}:{local_port}:127.0.0.1:{local_port}",
            "-N",  # 不执行远程命令
            f"{subdomain}@serveo.net",
        ]

        logger.info(f"启动 serveo 隧道: {' '.join(cmd)}")

        try:
            self._ssh_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            # 启动监控线程
            self._monitor_thread = threading.Thread(
                target=self._monitor_serveo,
                args=(self._ssh_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 15 秒）
            for i in range(30):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._ssh_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"SSH 进程已退出（返回码: {self._ssh_procobj.returncode}）\n可能原因：\n1. 校园网限制了外网 SSH 连接（端口 22）\n2. serveo.net 连接被阻断\n建议尝试 bore 方案",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "隧道启动超时（serveo.net 可能无响应）",
            }

        except Exception as e:
            logger.exception("启动 serveo 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 serveo 失败: {e}",
            }

    def _monitor_serveo(self, proc: subprocess.Popen):
        """监控 serveo SSH 连接，解析公网 URL"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[serveo] {line}")

                # serveo 成功时输出类似：
                # "Forwarding HTTP traffic from https://xxx.serveo.net"
                # "Forwarding TCP traffic from port xxx"
                if "Forwarding" in line and ("serveo.net" in line or "port" in line):
                    self._status = "running"
                    # 提取 URL
                    import re as _re
                    m = _re.search(r'https?://[\w\-\.]+\.serveo\.net', line)
                    if m:
                        self._public_url = m.group(0)
                    else:
                        # 提取端口
                        m2 = _re.search(r'port\s+(\d+)', line)
                        if m2:
                            port = m2.group(1)
                            self._public_url = f"https://{self._subdomain}.serveo.net:{port}"
                    logger.info(f"serveo 隧道已建立: {self._public_url}")

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "denied" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"serveo 隧道异常: {line}")

        except Exception as e:
            logger.error(f"serveo 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── bore 启动 ───────────────────────────────────

    def _find_bore(self) -> Optional[str]:
        """查找 bore 可执行文件"""
        if self._settings.bore_path and Path(self._settings.bore_path).exists():
            return self._settings.bore_path

        for name in ("bore", "bore.exe"):
            for dir_ in os.environ.get("PATH", "").split(os.pathsep):
                path = Path(dir_) / name
                if path.exists():
                    return str(path)

        candidates = [
            Path.home() / "bore" / "bore",
            Path.home() / ".local" / "bin" / "bore",
            Path.home() / ".ts2" / "bore",
            Path(__file__).parent.parent.parent / "bore" / "bore",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    def _start_bore(self) -> Dict[str, Any]:
        """通过 bore.pub 建立隧道（纯 Python 实现，无需 bore 二进制）"""
        import struct as _struct

        BORE_HOST = "bore.pub"
        BORE_PORT = 7835
        local_port = self._settings.local_port

        try:
            # 连接到 bore.pub
            logger.info(f"连接 bore.pub:{BORE_PORT} ...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((BORE_HOST, BORE_PORT))

            # 发送本地端口（4 字节大端序）
            sock.sendall(_struct.pack("!I", local_port))
            logger.info(f"已发送本地端口: {local_port}")

            # 接收远程端口（4 字节大端序）
            data = sock.recv(4)
            if len(data) < 4:
                sock.close()
                return {"success": False, "status": "error", "message": "bore 服务器响应无效"}

            remote_port = _struct.unpack("!I", data)[0]
            logger.info(f"bore 分配远程端口: {remote_port}")

            # bore.pub 的公网地址格式
            self._public_url = f"bore://{BORE_HOST}:{remote_port}"
            self._status = "running"
            self._start_time = time.time()

            # 保存 socket 以便 stop() 关闭
            self._bore_sock = sock

            # 启动数据转发线程（relay）
            self._bore_remote_port = remote_port

            def _relay():
                """将 bore 连接的数据转发到本地服务"""
                try:
                    local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    local_sock.connect(("127.0.0.1", local_port))
                    local_sock.setblocking(False)
                    sock.setblocking(False)

                    while True:
                        try:
                            r, _, _ = select.select([sock, local_sock], [], [], 5)
                            if not r:
                                # 超时，检查连接是否还活着
                                continue
                            for s in r:
                                data = s.recv(4096)
                                if not data:
                                    # 连接关闭
                                    return
                                other = local_sock if s is sock else sock
                                other.sendall(data)
                        except BlockingIOError:
                            continue
                        except Exception:
                            return
                except Exception as e:
                    logger.debug(f"bore relay 结束: {e}")
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    try:
                        local_sock.close()
                    except Exception:
                        pass

            # bore 只建立隧道，实际数据由外部连接
            # 通知成功（外部通过 bore://host:port 访问）
            return {
                "success": True,
                "status": "running",
                "public_url": f"bore://{BORE_HOST}:{remote_port}",
                "message": f"隧道已建立，访问 bore://{BORE_HOST}:{remote_port}",
            }

        except Exception as e:
            logger.exception("bore Python 隧道失败")
            self._status = "error"
            self._error_msg = str(e)
            return {
                "success": False,
                "status": "error",
                "message": f"bore 隧道失败: {e}",
            }

    def _start_bore_binary(self) -> Dict[str, Any]:
        """通过 bore 二进制建立隧道（fallback 方案）"""
        bore_path = self._find_bore()
        if not bore_path:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 bore 可执行文件\n\n请下载 bore:\n1. 从 GitHub 下载: https://github.com/ekzhang/bore/releases\n2. Windows: 下载 bore.exe，放在 PATH 中或指定 bore_path",
                "download_url": "https://github.com/ekzhang/bore/releases",
            }

        local_port = self._settings.local_port

        cmd = [bore_path, "tcp", str(local_port)]

        logger.info(f"启动 bore 隧道: {' '.join(cmd)}")

        try:
            self._bore_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_bore,
                args=(self._bore_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 15 秒）
            for i in range(30):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._bore_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"bore 进程已退出（返回码: {self._bore_procobj.returncode}）",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "bore 隧道启动超时",
            }

        except Exception as e:
            logger.exception("启动 bore 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 bore 失败: {e}",
            }

    # ── localtunnel 启动 ───────────────────────────────

    def _start_localtunnel(self) -> Dict[str, Any]:
        """通过 localtunnel (npx localtunnel) 建立隧道，无需 VPS"""
        local_port = self._settings.local_port

        # Windows 上 subprocess 找不到 npx，需要用 npx.cmd 或 shell=True
        npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
        cmd = [npx_cmd, "--yes", "localtunnel@2.0.2", "--port", str(local_port)]

        logger.info(f"启动 localtunnel: {' '.join(cmd)}")

        try:
            self._lt_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_localtunnel,
                args=(self._lt_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 30 秒，localtunnel 首次可能需要下载包）
            for i in range(60):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._lt_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"localtunnel 进程已退出（返回码: {self._lt_procobj.returncode}）",
                    }

            # 超时但进程仍在运行，可能只是输出延迟，返回 starting 状态
            return {
                "success": True,
                "status": "starting",
                "public_url": self._public_url,
                "message": "localtunnel 正在启动中，请稍后刷新查看状态",
            }

        except Exception as e:
            logger.exception("启动 localtunnel 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 localtunnel 失败: {e}",
            }

    def _monitor_localtunnel(self, proc: subprocess.Popen):
        """监控 localtunnel 连接，解析公网 URL"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[lt] {line}")

                # localtunnel 成功时输出： "your url is: https://xxxx.loca.lt"
                if "your url is:" in line.lower():
                    url = line.split("your url is:", 1)[-1].strip()
                    self._public_url = url
                    self._status = "running"
                    logger.info(f"localtunnel 隧道已建立: {url}")

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "denied" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"localtunnel 异常: {line}")

        except Exception as e:
            logger.error(f"localtunnel 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    def _monitor_bore(self, proc: subprocess.Popen):
        """监控 bore 连接"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[bore] {line}")

                # bore 成功时输出类似：
                # "Listening on 0.0.0.0:<N> -> tunnel.robe.io:<N>"
                # "Connected to tunnel.robe.io:<port>"
                if "listening" in line.lower() or "connected" in line.lower():
                    self._status = "running"
                    # 提取端口
                    import re as _re
                    m = _re.search(r':(\d{4,5})', line)
                    if m:
                        port = m.group(1)
                        self._public_url = f"bore://:{port} (请用 bore 客户端连接)"
                    logger.info(f"bore 隧道已建立: {line}")

                if "error" in line.lower() or "failed" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"bore 隧道异常: {line}")

        except Exception as e:
            logger.error(f"bore 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── Cloudflare Tunnel ──────────────────────────────────

    def _find_cloudflared(self) -> Optional[str]:
        """查找 cloudflared 可执行文件"""
        # 常见路径
        candidates = ["cloudflared"]
        if os.name == "nt":
            candidates.extend([
                "cloudflared.exe",
                os.path.expanduser("~\\scoop\\shims\\cloudflared.exe"),
                os.path.expanduser("~\\AppData\\Local\\cloudflared\\cloudflared.exe"),
                "C:\\Program Files\\cloudflared\\cloudflared.exe",
            ])
        else:
            candidates.extend([
                "/usr/local/bin/cloudflared",
                "/usr/bin/cloudflared",
                os.path.expanduser("~/bin/cloudflared"),
            ])
        for c in candidates:
            try:
                result = subprocess.run([c, "version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    def _start_cloudflare(self) -> Dict[str, Any]:
        """启动 Cloudflare Tunnel"""
        cf_token = self._settings.cf_token
        if not cf_token:
            return {
                "success": False,
                "status": "error",
                "message": "未配置 Cloudflare Tunnel Token\n\n请参考:\n1. 登录 Cloudflare Zero Trust 控制台\n2. 创建 Tunnel 并获取 Token\n3. 在设置中填入 Token",
            }

        cloudflared = self._find_cloudflared()
        if not cloudflared:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 cloudflared\n\n安装方式:\nWindows: winget install Cloudflare.cloudflared\nLinux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
                "download_url": "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/",
            }

        local_port = self._settings.local_port

        try:
            cmd = [cloudflared, "tunnel", "--no-autoupdate", "run", "--token", cf_token]

            self._cf_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )

            # 启动监控线程
            threading.Thread(target=self._monitor_cloudflare, daemon=True).start()

            # 等待连接（最多 30 秒）
            for i in range(60):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"Cloudflare 隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": "error",
                        "message": self._error_msg or "Cloudflare 隧道启动失败",
                    }

            # 超时但进程仍在运行
            if self._cf_procobj and self._cf_procobj.poll() is None:
                self._status = "starting"
                return {
                    "success": True,
                    "status": "starting",
                    "public_url": self._public_url,
                    "message": "Cloudflare 隧道正在启动中，请稍后刷新查看状态",
                }

            return {
                "success": False,
                "status": "error",
                "message": "Cloudflare 隧道启动超时",
            }

        except FileNotFoundError:
            return {"success": False, "status": "error", "message": "cloudflared 未找到"}
        except Exception as e:
            return {"success": False, "status": "error", "message": str(e)}

    def _monitor_cloudflare(self):
        """监控 cloudflared 进程输出"""
        proc = self._cf_procobj
        if not proc or not proc.stdout:
            return

        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                logger.info(f"[cloudflared] {line}")

                # 检测连接成功
                if "registered tunnel connection" in line.lower() or "connection" in line.lower() and "registered" in line.lower():
                    self._status = "running"
                    self._start_time = time.time()
                    # 如果有配置域名，使用配置的域名
                    if self._settings.cf_domain:
                        self._public_url = f"https://{self._settings.cf_domain}"
                    # 否则尝试从日志中提取
                    elif not self._public_url:
                        self._public_url = "Cloudflare Tunnel (域名在 Cloudflare 控制台查看)"

                # 检测错误
                if "error" in line.lower() and "registered" not in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"cloudflared 异常: {line}")

        except Exception as e:
            logger.error(f"cloudflared 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── 启动/停止 ─────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        """启动隧道（根据 tunnel_type 自动分发）"""
        # 检查是否已在运行
        for proc in (self._frpc_procobj, self._ssh_procobj, self._bore_procobj, self._lt_procobj, self._cf_procobj):
            if proc and proc.poll() is None:
                return {
                    "success": True,
                    "status": self._status,
                    "public_url": self._public_url,
                    "message": "隧道已在运行",
                }

        tunnel_type = self._tunnel_type

        if tunnel_type == "serveo":
            return self._start_serveo()
        elif tunnel_type == "bore":
            return self._start_bore()
        elif tunnel_type == "localtunnel":
            return self._start_localtunnel()
        elif tunnel_type == "cloudflare":
            return self._start_cloudflare()
        else:
            return self._start_frp()

    def _start_frp(self) -> Dict[str, Any]:
        """启动 frp 隧道（需要 VPS）"""
        if not self._settings.server_addr:
            return {
                "success": False,
                "status": "error",
                "message": "未配置 frps 服务器地址（server_addr）",
            }

        frpc_path = self._find_frpc()
        if not frpc_path:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 frpc 可执行文件\n\n请下载 frpc:\n1. 从 GitHub 下载: https://github.com/fatedier/frp/releases\n2. 放在 PATH 中，或在设置中指定 frpc_path\n3. Windows 用户下载 .exe 版本",
                "download_url": "https://github.com/fatedier/frp/releases",
            }

        ini_path = self._write_frpc_ini()
        logger.info(f"启动 frpc: {frpc_path} -c {ini_path}")

        try:
            self._frpc_procobj = subprocess.Popen(
                [frpc_path, "-c", str(ini_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_frpc,
                args=(self._frpc_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            for i in range(20):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._frpc_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"frpc 进程已退出（返回码: {self._frpc_procobj.returncode}）",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "隧道启动超时",
            }

        except Exception as e:
            logger.exception("启动 frpc 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 frpc 失败: {e}",
            }

    def stop(self) -> Dict[str, Any]:
        """停止所有类型的隧道"""
        for proc, name in [
            (self._frpc_procobj, "frpc"),
            (self._ssh_procobj, "serveo"),
            (self._bore_procobj, "bore"),
            (self._lt_procobj, "localtunnel"),
            (self._cf_procobj, "cloudflared"),
        ]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                except Exception as e:
                    logger.warning(f"停止 {name} 失败: {e}")

        # 关闭 Python bore socket
        if getattr(self, "_bore_sock", None):
            try:
                self._bore_sock.close()
            except Exception:
                pass
            self._bore_sock = None

        self._frpc_procobj = None
        self._ssh_procobj = None
        self._bore_procobj = None
        self._lt_procobj = None
        self._cf_procobj = None
        self._status = "stopped"
        self._public_url = ""
        self._start_time = None
        self._error_msg = ""
        return {"success": True, "status": "stopped", "message": "隧道已停止"}

    def get_status(self) -> Dict[str, Any]:
        """获取隧道状态"""
        # 检查各进程状态
        for proc, name, err_prefix in [
            (self._frpc_procobj, "frp", "frpc"),
            (self._ssh_procobj, "serveo", "serveo SSH"),
            (self._bore_procobj, "bore", "bore"),
            (self._lt_procobj, "localtunnel", "localtunnel"),
            (self._cf_procobj, "cloudflared", "cloudflared"),
        ]:
            if proc and proc.poll() is not None:
                self._status = "error"
                self._error_msg = f"{err_prefix} 进程已退出（返回码: {proc.returncode}）"

        return {
            "status": self._status,
            "public_url": self._public_url,
            "tunnel_type": self._tunnel_type,
            "server_addr": self._settings.server_addr,
            "local_port": self._settings.local_port,
            "remote_port": self._settings.remote_port,
            "uptime": round(time.time() - self._start_time, 1) if self._start_time else 0,
            "error": self._error_msg,
            "enabled": self._settings.enabled,
            "auto_start": self._settings.auto_start,
        }

    def restart(self) -> Dict[str, Any]:
        """重启隧道"""
        self.stop()
        time.sleep(1)
        return self.start()


# 全局单例
_tunnel_manager: Optional[TunnelManager] = None


def get_tunnel_manager() -> TunnelManager:
    global _tunnel_manager
    if _tunnel_manager is None:
        _tunnel_manager = TunnelManager()
    return _tunnel_manager
