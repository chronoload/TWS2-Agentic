"""
网络访问控制与防火墙管理
参考思源笔记的网络设置：允许/禁止公用网络访问、自动配置防火墙规则
跨平台支持：Windows / macOS / Linux
"""

import logging
import platform
import socket
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_DIR = Path.home() / ".ts2"
CONFIG_FILE = CONFIG_DIR / "network_settings.json"

FIREWALL_RULE_NAME = "TS2 Server"


class NetworkSettings:
    """网络访问设置（参考思源笔记的网络配置）"""

    def __init__(self):
        self.allow_lan: bool = True          # 允许局域网访问
        self.allow_public_network: bool = True  # 允许公用网络访问
        self.allow_usb: bool = True           # 允许 USB 连接（adb reverse）
        self.host: str = "0.0.0.0"           # 监听地址
        self.port: int = 6906                # 监听端口
        self.firewall_configured: bool = False  # 防火墙是否已配置
        self._load()

    def _load(self):
        """加载配置"""
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.allow_lan = data.get("allow_lan", self.allow_lan)
            self.allow_public_network = data.get("allow_public_network", self.allow_public_network)
            self.allow_usb = data.get("allow_usb", self.allow_usb)
            self.host = data.get("host", self.host)
            self.port = data.get("port", self.port)
            self.firewall_configured = data.get("firewall_configured", self.firewall_configured)
        except Exception as e:
            logger.warning(f"Load network settings failed: {e}")

    def save(self):
        """保存配置"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "allow_lan": self.allow_lan,
            "allow_public_network": self.allow_public_network,
            "allow_usb": self.allow_usb,
            "host": self.host,
            "port": self.port,
            "firewall_configured": self.firewall_configured,
        }
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_effective_host(self) -> str:
        """根据设置返回实际监听地址"""
        if not self.allow_lan and not self.allow_public_network:
            return "127.0.0.1"
        return self.host

    def to_dict(self) -> dict:
        return {
            "allow_lan": self.allow_lan,
            "allow_public_network": self.allow_public_network,
            "allow_usb": self.allow_usb,
            "host": self.get_effective_host(),
            "port": self.port,
            "firewall_configured": self.firewall_configured,
            "platform": platform.system(),
        }


def get_all_network_interfaces() -> List[Dict[str, str]]:
    """获取所有网络接口及 IP 地址"""
    interfaces = []
    try:
        hostname = socket.gethostname()
        # 获取所有 IP 地址
        addrs = socket.getaddrinfo(hostname, None)
        seen = set()
        for addr in addrs:
            ip = addr[4][0]
            if ip in seen or ip.startswith("127.") or ":" in ip:
                continue
            seen.add(ip)
            interfaces.append({
                "ip": ip,
                "family": "IPv4",
            })
    except Exception as e:
        logger.warning(f"Get network interfaces failed: {e}")
    return interfaces


def get_network_profiles() -> List[Dict[str, str]]:
    """获取网络配置文件类别（仅 Windows）"""
    profiles = []
    if platform.system() != "Windows":
        return profiles
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-NetConnectionProfile | Select-Object Name, NetworkCategory, IPv4Connectivity | ConvertTo-Json"],
            capture_output=True, timeout=10
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if text:
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                profiles.append({
                    "name": item.get("Name", ""),
                    "category": item.get("NetworkCategory", ""),
                    "connectivity": item.get("IPv4Connectivity", ""),
                })
    except Exception as e:
        logger.warning(f"Get network profiles failed: {e}")
    return profiles


def configure_firewall(port: int, allow: bool = True) -> Tuple[bool, str]:
    """
    配置防火墙规则（跨平台）
    
    Returns:
        (success, message)
    """
    system = platform.system()

    if system == "Windows":
        return _configure_firewall_windows(port, allow)
    elif system == "Darwin":
        return _configure_firewall_macos(port, allow)
    elif system == "Linux":
        return _configure_firewall_linux(port, allow)
    else:
        return False, f"Unsupported platform: {system}"


def _configure_firewall_windows(port: int, allow: bool) -> Tuple[bool, str]:
    """Windows 防火墙配置"""
    action = "allow" if allow else "block"
    direction = "in"
    logger.info(f"[防火墙] 开始配置 Windows 防火墙, port={port}, allow={allow}")

    try:
        # 检查规则是否已存在
        check = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}"],
            capture_output=True, timeout=5
        )
        stdout_text = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
        stderr_text = check.stderr.decode("utf-8", errors="replace") if check.stderr else ""
        rule_exists = "No rules match" not in stdout_text and check.returncode == 0
        logger.info(f"[防火墙] 规则检查结果: exists={rule_exists}, stdout_len={len(stdout_text)}")

        if allow:
            if rule_exists:
                # 规则已存在：更新端口和 profile（确保所有网络类型都被放行）
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "set", "rule",
                     f"name={FIREWALL_RULE_NAME}", "new",
                     f"dir={direction}", f"action={action}",
                     "protocol=TCP", f"localport={port}",
                     "profile=domain,private,public"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                logger.info(f"[防火墙] 更新规则: returncode={result.returncode}, stdout={stdout[:100]}, stderr={stderr[:100]}")
                if result.returncode == 0:
                    return True, f"防火墙规则已更新（端口 {port}/TCP，覆盖域/专用/公用网络）"
                else:
                    return False, f"更新防火墙规则失败: {stderr.strip() or stdout.strip()}"
            else:
                # 规则不存在：新增
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "add", "rule",
                     f"name={FIREWALL_RULE_NAME}", f"dir={direction}", f"action={action}",
                     "protocol=TCP", f"localport={port}",
                     "profile=domain,private,public"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                logger.info(f"[防火墙] 添加规则: returncode={result.returncode}, stdout={stdout[:100]}, stderr={stderr[:100]}")
                if result.returncode == 0:
                    return True, f"防火墙规则已添加（端口 {port}/TCP，覆盖域/专用/公用网络）"
                else:
                    if "requires elevation" in stderr.lower() or "access is denied" in stderr.lower():
                        return False, "需要管理员权限。请以管理员身份运行程序，或手动执行：\nnetsh advfirewall firewall add rule name=\"TS2 Server\" dir=in action=allow protocol=TCP localport={port} profile=domain,private,public".format(port=port)
                    return False, f"添加防火墙规则失败: {stderr.strip() or stdout.strip()}"
        else:
            if rule_exists:
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule",
                     f"name={FIREWALL_RULE_NAME}"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                logger.info(f"[防火墙] 删除规则: returncode={result.returncode}, stdout={stdout[:100]}")
                if result.returncode == 0:
                    return True, "防火墙规则已删除"
                return False, f"删除防火墙规则失败: {stdout.strip()}"
            return True, "无需删除（规则不存在）"

    except subprocess.TimeoutExpired:
        return False, "防火墙配置超时"
    except Exception as e:
        logger.exception("[防火墙] 配置异常")
        return False, f"防火墙配置失败: {e}"


def _configure_firewall_macos(port: int, allow: bool) -> Tuple[bool, str]:
    """macOS 防火墙配置（pfctl）"""
    try:
        anchor_name = "ts2_server"

        if allow:
            # 添加 pf 规则允许端口
            rule = f"pass in proto tcp from any to any port {port}\n"
            result = subprocess.run(
                ["sudo", "pfctl", "-ef", anchor_name, "-f", "-"],
                input=rule.encode(), capture_output=True, timeout=10
            )
            # macOS 防火墙通常默认允许，主要确保应用不被阻止
            # 检查应用防火墙
            check = subprocess.run(
                ["sudo", "/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                capture_output=True, timeout=5
            )
            output = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
            if "enabled" in output.lower():
                return True, f"macOS 防火墙已启用，端口 {port} 需要在系统设置中允许 Python"
            return True, f"macOS 防火墙未启用，端口 {port} 可直接访问"
        else:
            return True, "macOS 防火墙规则已移除"

    except subprocess.TimeoutExpired:
        return False, "防火墙配置超时"
    except Exception as e:
        return False, f"macOS 防火墙配置失败: {e}"


def _configure_firewall_linux(port: int, allow: bool) -> Tuple[bool, str]:
    """Linux 防火墙配置（iptables/ufw/firewalld）"""
    messages = []

    # 尝试 ufw
    try:
        check_ufw = subprocess.run(["which", "ufw"], capture_output=True, timeout=3)
        if check_ufw.returncode == 0:
            if allow:
                result = subprocess.run(
                    ["sudo", "ufw", "allow", f"{port}/tcp"],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    messages.append(f"ufw: 端口 {port}/TCP 已放行")
                else:
                    messages.append("ufw: 需要 sudo 权限")
            else:
                subprocess.run(["sudo", "ufw", "delete", "allow", f"{port}/tcp"],
                               capture_output=True, timeout=10)
                messages.append("ufw: 规则已删除")
    except Exception:
        pass

    # 尝试 firewalld
    try:
        check_firewalld = subprocess.run(["which", "firewall-cmd"], capture_output=True, timeout=3)
        if check_firewalld.returncode == 0:
            if allow:
                result = subprocess.run(
                    ["sudo", "firewall-cmd", "--permanent", "--add-port", f"{port}/tcp"],
                    capture_output=True, timeout=10
                )
                subprocess.run(["sudo", "firewall-cmd", "--reload"],
                               capture_output=True, timeout=10)
                if result.returncode == 0:
                    messages.append(f"firewalld: 端口 {port}/TCP 已放行")
                else:
                    messages.append("firewalld: 需要 sudo 权限")
            else:
                subprocess.run(["sudo", "firewall-cmd", "--permanent", "--remove-port", f"{port}/tcp"],
                               capture_output=True, timeout=10)
                subprocess.run(["sudo", "firewall-cmd", "--reload"],
                               capture_output=True, timeout=10)
                messages.append("firewalld: 规则已删除")
    except Exception:
        pass

    # 尝试 iptables
    try:
        check_iptables = subprocess.run(["which", "iptables"], capture_output=True, timeout=3)
        if check_iptables.returncode == 0 and not messages:
            if allow:
                result = subprocess.run(
                    ["sudo", "iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    messages.append(f"iptables: 端口 {port}/TCP 已放行")
                else:
                    messages.append("iptables: 需要 sudo 权限")
            else:
                subprocess.run(
                    ["sudo", "iptables", "-D", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                    capture_output=True, timeout=10
                )
                messages.append("iptables: 规则已删除")
    except Exception:
        pass

    if messages:
        return True, "; ".join(messages)
    return False, "未找到可用的防火墙工具（ufw/firewalld/iptables）"


def set_network_profile_private() -> Tuple[bool, str]:
    """
    将 Windows 网络配置文件设为"专用"（允许局域网发现和访问）
    参考思源笔记：自动将网络设为专用以允许局域网访问
    """
    if platform.system() != "Windows":
        return True, "非 Windows 平台，无需设置"

    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Set-NetConnectionProfile -NetworkCategory Private"],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return True, "网络配置文件已设为专用"
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        if "access denied" in stderr.lower() or "requires elevation" in stderr.lower():
            return False, "需要管理员权限设置网络类别"
        return False, f"设置失败: {stderr.strip()}"
    except Exception as e:
        return False, f"设置失败: {e}"


def check_network_access(port: int) -> Dict[str, any]:
    """
    检查网络访问状态
    返回各接口的可访问性
    """
    result = {
        "localhost_accessible": False,
        "lan_accessible": False,
        "interfaces": get_all_network_interfaces(),
        "profiles": get_network_profiles(),
        "firewall_rule_exists": False,
        "recommendations": [],
    }

    # 检查 localhost
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", port))
        s.close()
        result["localhost_accessible"] = True
    except Exception:
        result["recommendations"].append("服务器未在 localhost 启动")

    # 检查局域网 IP
    for iface in result["interfaces"]:
        ip = iface["ip"]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.close()
            result["lan_accessible"] = True
            iface["accessible"] = True
        except Exception:
            iface["accessible"] = False
            result["recommendations"].append(f"无法通过 {ip} 访问服务器")

    # 检查防火墙规则
    if platform.system() == "Windows":
        try:
            check = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}"],
                capture_output=True, timeout=5
            )
            stdout_text = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
            result["firewall_rule_exists"] = "No rules match" not in stdout_text and check.returncode == 0
        except Exception:
            pass

    # 生成建议
    if not result["lan_accessible"]:
        if not result["firewall_rule_exists"]:
            result["recommendations"].append("防火墙规则未配置，请点击\"配置防火墙\"按钮")
        for profile in result["profiles"]:
            if profile.get("category") == "Public":
                result["recommendations"].append(
                    f"网络 \"{profile['name']}\" 是公用网络，建议设为专用网络以允许局域网访问"
                )

    return result
