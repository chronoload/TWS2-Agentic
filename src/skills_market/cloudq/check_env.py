#!/usr/bin/env python3
"""
腾讯云智能顾问环境检测脚本

功能：检测 Python 版本、Skill 版本更新（含 changelog）、密钥、智能顾问开通状态、角色配置状态，输出检测结果
      支持 --enable-advisor 参数开通智能顾问（写入操作，需用户明确同意）

用法:
    python3 check_env.py           # 标准模式：输出详细检测结果
    python3 check_env.py --quiet   # 静默模式：仅输出错误信息（供其他脚本调用）
    python3 check_env.py --skip-update  # 跳过版本更新检查
    python3 check_env.py --enable-advisor  # 开通智能顾问（写入操作，需用户明确同意）
    python3 check_env.py --list-console-roles  # 列出支持控制台登录的角色（JSON）
    python3 check_env.py --check-role <name>   # 检查指定角色是否支持控制台登录（JSON）

返回码:
    0 - 环境就绪（密钥 + 智能顾问已开通 + 角色全部正常）/ 查询成功
    1 - Python 版本不满足 / 查询失败
    2 - AK/SK 未配置或无效
    3 - 角色未配置（需要执行角色创建步骤，可选）
    4 - 智能顾问未开通（需要开通智能顾问后才能使用 CloudQ）

跨平台支持: Windows / Linux / macOS
"""

import json
import os
import platform
import stat
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# 将 scripts 目录加入搜索路径
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from tcloud_api import call_api  # noqa: E402


# ============== 配置 ==============
CONFIG_DIR = Path.home() / ".tencent-cloudq"
CONFIG_FILE = CONFIG_DIR / "config.json"
VERSION_CACHE_FILE = CONFIG_DIR / "version_check_cache.json"
ADVISOR_ROLE_NAME = "advisor"

# 角色需要关联的策略列表（用于检测和自动补充）
REQUIRED_ROLE_POLICIES = [
    "QcloudTAGFullAccess",
    "QcloudAdvisorFullAccess",
]

# 版本检查配置
META_FILE = SCRIPT_DIR / "_meta.json"
VERSION_CHECK_TIMEOUT = 15  # 秒


# ============== 输出函数 ==============
QUIET_MODE = "--quiet" in sys.argv
SKIP_UPDATE = "--skip-update" in sys.argv
ENABLE_ADVISOR = "--enable-advisor" in sys.argv


def log_info(msg: str):
    if not QUIET_MODE:
        print(msg)


def log_ok(msg: str):
    if not QUIET_MODE:
        print(f"  [OK] {msg}")


def log_warn(msg: str):
    if not QUIET_MODE:
        print(f"  [WARN] {msg}")


def log_fail(msg: str):
    print(f"  [FAIL] {msg}")


def log_section(title: str):
    if not QUIET_MODE:
        print(f"\n=== {title} ===")


def save_config(account_uin: str, role_name: str, role_arn: str,
                auto_created: bool = False, role_id: str = ""):
    """保存配置文件（跨平台兼容）"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 设置目录权限（非 Windows）
    if platform.system() != "Windows":
        try:
            os.chmod(str(CONFIG_DIR), stat.S_IRWXU)  # 700
        except OSError:
            pass

    config = {
        "accountUin": account_uin,
        "roleName": role_name,
        "roleArn": role_arn,
        "configuredAt": datetime.now(timezone.utc).isoformat(),
        "autoCreated": auto_created,
        "version": "1.0",
    }
    if role_id:
        config["roleId"] = role_id

    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # 设置文件权限（非 Windows）
    if platform.system() != "Windows":
        try:
            os.chmod(str(CONFIG_FILE), stat.S_IRUSR | stat.S_IWUSR)  # 600
        except OSError:
            pass


def ensure_role_policies(role_name: str) -> list:
    """为角色补充缺失的必需策略（幂等操作）。

    对 REQUIRED_ROLE_POLICIES 中的每个策略执行 AttachRolePolicy，
    已关联的策略会返回 PolicyAlreadyAttached 错误码，视为成功。

    Returns:
        list: 关联失败的警告信息列表（空列表表示全部成功）
    """
    warnings = []
    for policy_name in REQUIRED_ROLE_POLICIES:
        attach_result = call_api(
            "cam", "cam.tencentcloudapi.com",
            "AttachRolePolicy", "2019-01-16",
            {"AttachRoleName": role_name, "PolicyName": policy_name},
        )
        if not attach_result.get("success"):
            err_code = attach_result.get("error", {}).get("code", "")
            if "AlreadyAttached" not in err_code:
                err_msg = attach_result.get("error", {}).get("message", "未知错误")
                warnings.append(f"策略 {policy_name} 关联失败: {err_msg}")
    return warnings


def list_console_login_roles() -> dict:
    """查询账号下所有支持控制台登录的用户自定义角色（只读）。

    Returns:
        dict: {
            "success": bool,
            "roles": [{"RoleName": ..., "ConsoleLogin": 1, ...}, ...],
            "total": int,  # 筛选后数量
            "error": {...}  # 仅失败时
        }
    """
    result = call_api(
        "cam", "cam.tencentcloudapi.com",
        "DescribeRoleList", "2019-01-16",
        {"Page": 1, "Rp": 200},
    )
    if not result.get("success"):
        return {
            "success": False,
            "roles": [],
            "error": result.get("error", {}),
        }
    role_list = result.get("data", {}).get("List", [])
    console_roles = [
        r for r in role_list
        if r.get("ConsoleLogin") == 1 and r.get("RoleType") == "user"
    ]
    return {"success": True, "roles": console_roles, "total": len(console_roles)}


def check_role_console_login(role_name: str) -> dict:
    """检查指定角色是否存在及是否支持控制台登录（只读）。

    Args:
        role_name: 角色名称

    Returns:
        dict: {
            "success": bool,   # API 调用是否成功
            "role_name": str,
            "exists": bool,    # 角色是否存在
            "console_login": bool,  # 是否支持控制台登录
            "data": {...}      # 角色完整数据（仅存在时）
        }
    """
    result = call_api(
        "cam", "cam.tencentcloudapi.com",
        "GetRole", "2019-01-16",
        {"RoleName": role_name},
    )
    if not result.get("success"):
        return {
            "success": False,
            "role_name": role_name,
            "exists": False,
            "console_login": False,
            "error": result.get("error", {}),
        }
    data = result.get("data", {})
    console_login = data.get("ConsoleLogin", 0) == 1
    return {
        "success": True,
        "role_name": role_name,
        "exists": True,
        "console_login": console_login,
        "data": data,
    }


def parse_version(version_str: str) -> tuple:
    """解析语义化版本号字符串为可比较的元组，如 '1.3.0' -> (1, 3, 0)"""
    try:
        parts = version_str.strip().lstrip("v").split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def get_local_version() -> tuple:
    """读取本地 _meta.json 中的版本号，返回 (slug, version_str) 或 (None, None)"""
    if not META_FILE.exists():
        return None, None
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        return meta.get("slug"), meta.get("version")
    except (json.JSONDecodeError, IOError):
        return None, None


def _extract_version(data: dict) -> str | None:
    """从 ClawHub API / inspect JSON 中提取 latestVersion.version"""
    return data.get("latestVersion", {}).get("version")


def _get_info_via_requests(api_url: str) -> dict | None:
    """L1: 通过 requests 库直接请求 ClawHub API（自带 certifi，SSL 兼容性最好）"""
    import requests  # noqa: delay import
    resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=VERSION_CHECK_TIMEOUT)
    if resp.status_code != 200:
        return None
    return resp.json()


def _get_info_via_clawhub(slug: str) -> dict | None:
    """L2: 通过本地已安装的 clawhub CLI 获取版本"""
    import subprocess
    result = subprocess.run(
        ["clawhub", "inspect", slug, "--versions", "--json"],
        capture_output=True, text=True, timeout=VERSION_CHECK_TIMEOUT,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def get_remote_info(slug: str) -> dict | None:
    """
    从 ClawHub registry 查询指定 slug 的最新版本信息（含 changelog），返回完整 JSON 或 None。

    两级降级策略（不执行 npx 等远程代码下载）：
      L1: requests 直接请求 API（最快，自带 SSL 证书）
      L2: clawhub inspect --versions（仅使用本地已安装的 CLI）
    """
    api_url = f"https://clawhub.ai/api/v1/skills/{urllib.parse.quote(slug, safe='')}"
    strategies = [
        lambda: _get_info_via_requests(api_url),
        lambda: _get_info_via_clawhub(slug),
    ]
    for strategy in strategies:
        try:
            data = strategy()
            if data and _extract_version(data):
                return data
        except Exception:
            continue
    return None


def _load_version_cache() -> dict | None:
    """读取版本检查缓存，返回缓存内容或 None"""
    if not VERSION_CACHE_FILE.exists():
        return None
    try:
        return json.loads(VERSION_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def _save_version_cache(result: dict):
    """保存版本检查结果到缓存文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cache = {
        "checked_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": result.get("status"),
        "local_version": result.get("local_version"),
        "remote_version": result.get("remote_version"),
        "changelog": result.get("changelog", []),
        "message": result.get("message"),
    }
    try:
        VERSION_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except IOError:
        pass


def check_version_update() -> dict:
    """
    检查本地版本与远端版本（两者独立，互不影响）。

    设计原则：
    - 本地版本获取失败不影响远端版本获取
    - 远端版本获取失败不影响本地版本获取
    - 两者结果都展示给用户，让用户自主决定是否更新

    返回 dict:
      - status: "up_to_date" | "update_available" | "local_only" | "remote_only" |
               "both_available" | "check_failed_local" | "check_failed_remote" | "both_failed"
      - local_version: 本地版本号（str 或 None）
      - remote_version: 远端版本号（str 或 None）
      - slug: skill 标识符
      - changelog: 新版本的变更日志列表（有更新时）
      - message: 可读的状态说明
      - local_error: 本地版本获取错误信息（仅失败时）
      - remote_error: 远端版本获取错误信息（仅失败时）
    """
    # ---- 独立步骤1：获取本地版本 ----
    slug, local_ver = get_local_version()
    local_error = None
    if not slug or not local_ver:
        local_error = "未找到 _meta.json 或版本信息缺失（文件不存在或格式错误）"
        log_warn(f"本地版本检查: {local_error}")

    # ---- 独立步骤2：获取远端版本 ----
    remote_ver = None
    remote_data = None
    remote_error = None

    # 优先使用本地 slug，若本地无则尝试常见 slug 列表
    slugs_to_try = [slug] if slug else ["cloudq", "CloudQ", "advisor", "tencent-cloudq"]
    slugs_to_try = [s for s in slugs_to_try if s]  # 过滤 None

    for try_slug in slugs_to_try:
        try:
            remote_data = get_remote_info(try_slug)
            if remote_data and _extract_version(remote_data):
                remote_ver = _extract_version(remote_data)
                if not slug:
                    slug = try_slug  # 记录实际使用的 slug
                break
        except Exception:
            continue

    if not remote_ver:
        remote_error = "无法获取远端版本信息（网络问题、接口不可用或 Slug 不匹配）"

    # ---- 合并结果并判断状态 ----
    result = {
        "local_version": local_ver,
        "remote_version": remote_ver,
        "slug": slug,
    }

    # 添加可选字段
    if local_error:
        result["local_error"] = local_error
    if remote_error:
        result["remote_error"] = remote_error

    # ---- 状态判断逻辑 ----
    has_local = bool(local_ver)
    has_remote = bool(remote_ver)

    if has_local and has_remote:
        # 两者都有：比较版本
        local_parsed = parse_version(local_ver)
        remote_parsed = parse_version(remote_ver)

        if remote_parsed <= local_parsed:
            result.update({
                "status": "up_to_date",
                "message": f"当前已是最新版本: {local_ver}",
            })
        else:
            # 收集 changelog
            changelog = _collect_changelog(remote_data, local_parsed)
            result.update({
                "status": "update_available",
                "changelog": changelog,
                "message": f"发现新版本: {local_ver} → {remote_ver}",
            })

    elif has_local and not has_remote:
        # 仅本地有，远端失败
        result.update({
            "status": "local_only",
            "message": f"本地版本: {local_ver}，但无法获取远端版本信息",
        })

    elif not has_local and has_remote:
        # 仅远端有，本地缺失
        changelog = []
        latest_changelog = (remote_data or {}).get("latestVersion", {}).get("changelog", "")
        if latest_changelog:
            changelog.append(f"  {remote_ver}: {latest_changelog}")

        result.update({
            "status": "remote_only",
            "changelog": changelog,
            "message": f"本地缺少版本元数据，检测到远端最新版本: {remote_ver}",
        })

    else:
        # 两者都失败
        result.update({
            "status": "both_failed",
            "message": "本地和远端版本信息均无法获取",
        })

    _save_version_cache(result)
    return result


def _collect_changelog(remote_data: dict, local_parsed: tuple) -> list:
    """从远端数据中收集比本地版本更新的 changelog"""
    changelog_lines = []
    versions = remote_data.get("versions", [])
    for v in versions:
        v_str = v.get("version", "")
        v_parsed = parse_version(v_str)
        if v_parsed > local_parsed:
            desc = v.get("changelog") or v.get("description") or ""
            if desc:
                changelog_lines.append(f"  {v_str}: {desc}")
            else:
                changelog_lines.append(f"  {v_str}")

    # 兜底：从 latestVersion.changelog 提取
    if not changelog_lines:
        latest_changelog = remote_data.get("latestVersion", {}).get("changelog", "")
        if latest_changelog:
            remote_ver = _extract_version(remote_data) or "未知"
            changelog_lines.append(f"  {remote_ver}: {latest_changelog}")

    return changelog_lines


def main():
    # ============== 独立命令行参数（直接输出 JSON 并退出） ==============
    args = sys.argv[1:]

    if "--list-console-roles" in args:
        result = list_console_login_roles()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("success") else 1)

    if "--check-role" in args:
        idx = args.index("--check-role")
        if idx + 1 >= len(args) or args[idx + 1].startswith("--"):
            print(json.dumps({"success": False, "error": "缺少角色名参数"}, ensure_ascii=False))
            sys.exit(1)
        role_name = args[idx + 1]
        result = check_role_console_login(role_name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("success") else 1)

    # ============== 1. 检查 Python 版本 ==============
    log_section("1. 检查运行环境")

    py_ver = sys.version_info
    if py_ver < (3, 7):
        log_fail(f"Python 版本过低: {sys.version}，需要 Python 3.7+")
        sys.exit(1)

    log_ok(f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro} ({platform.system()} {platform.machine()})")

    # ============== 2. 检查 Skill 版本更新 ==============
    log_section("2. 检查 Skill 版本")

    if SKIP_UPDATE:
        log_ok("已跳过版本更新检查（--skip-update）")
    else:
        ver_result = check_version_update()
        status = ver_result["status"]
        local_ver = ver_result.get("local_version")
        remote_ver = ver_result.get("remote_version")

        if status == "up_to_date":
            # 本地和远端都有，且已是最新
            log_ok(ver_result["message"])
            log_info(f"  本地版本: {local_ver} | 远端版本: {remote_ver}")

        elif status == "update_available":
            # 本地和远端都有，远端更新 - 必须提示用户更新
            log_warn(ver_result["message"])
            log_info("")
            log_info(f"  当前版本: {local_ver}")
            log_info(f"  最新版本: {remote_ver}")
            changelog = ver_result.get("changelog", [])
            if changelog:
                log_info("")
                log_info("  === Changelog（变更日志）===")
                for line in changelog:
                    log_info(line)
            log_info("")
            log_info("  请前往 SkillHub 或 ClawHub 更新此 Skill")
            log_info("")

        elif status == "local_only":
            # 仅本地有版本信息
            log_warn(ver_result["message"])
            log_info(f"  本地版本: {local_ver}")
            if ver_result.get("remote_error"):
                log_info(f"  远端检查: {ver_result['remote_error']}")
            log_info("  版本比较跳过（无法获取远端版本），继续后续检测...")

        elif status == "remote_only":
            # 仅远端有版本信息（本地缺失）
            log_warn(ver_result["message"])
            log_info("")
            log_info(f"  远端最新版本: {remote_ver}")
            if ver_result.get("local_error"):
                log_info(f"  本地检查: {ver_result['local_error']}")
            changelog = ver_result.get("changelog", [])
            if changelog:
                log_info("")
                log_info("  === Changelog（变更日志）===")
                for line in changelog:
                    log_info(line)
            log_info("")
            log_info("  建议：前往 SkillHub 或 ClawHub 下载/更新此 Skill")
            log_info("  当前仍可正常使用，但可能缺少最新功能或修复。")
            log_info("")

        elif status == "both_failed":
            # 两者都失败
            log_warn(ver_result["message"])
            if ver_result.get("local_error"):
                log_info(f"  本地: {ver_result['local_error']}")
            if ver_result.get("remote_error"):
                log_info(f"  远端: {ver_result['remote_error']}")
            log_info("  版本检查完全跳过，继续后续检测...")

        else:
            # 兜底：未知状态
            log_warn(f"版本检查返回未知状态: {status}")
            log_info("  继续后续检测...")

    # ============== 3. 检查 AK/SK 配置 ==============
    log_section("3. 检查 AK/SK 配置")

    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")

    if not secret_id or not secret_key:
        missing = []
        if not secret_id:
            missing.append("TENCENTCLOUD_SECRET_ID")
        if not secret_key:
            missing.append("TENCENTCLOUD_SECRET_KEY")
        log_fail(f"未配置以下环境变量: {', '.join(missing)}")
        log_info("")
        log_info("  请将腾讯云 API 密钥永久写入 shell 配置文件：")
        log_info("")
        log_info("  Linux / macOS（写入 ~/.bashrc 或 ~/.zshrc）:")
        log_info('    echo \'export TENCENTCLOUD_SECRET_ID="your-secret-id"\' >> ~/.bashrc')
        log_info('    echo \'export TENCENTCLOUD_SECRET_KEY="your-secret-key"\' >> ~/.bashrc')
        log_info("    source ~/.bashrc")
        log_info("")
        log_info("  Windows PowerShell（写入用户级环境变量）:")
        log_info('    [Environment]::SetEnvironmentVariable("TENCENTCLOUD_SECRET_ID", "your-secret-id", "User")')
        log_info('    [Environment]::SetEnvironmentVariable("TENCENTCLOUD_SECRET_KEY", "your-secret-key", "User")')
        log_info("")
        log_info("  密钥获取地址: https://console.cloud.tencent.com/cam/capi")
        sys.exit(2)

    masked_id = f"{secret_id[:4]}****{secret_id[-4:]}" if len(secret_id) > 8 else "****"
    log_ok(f"SecretId 已配置: {masked_id}")
    log_ok("SecretKey 已配置: ****")

    token = os.environ.get("TENCENTCLOUD_TOKEN", "")
    if token:
        log_ok("临时密钥 Token 已配置")

    # ============== 4. 验证 AK/SK 有效性 ==============
    log_section("4. 验证 AK/SK 有效性")

    verify_result = call_api(
        "advisor", "advisor.tencentcloudapi.com",
        "DescribeArchList", "2020-07-21",
        {"PageNumber": 1, "PageSize": 1},
        "ap-guangzhou",
    )

    if verify_result.get("success"):
        log_ok("AK/SK 验证通过，接口调用成功")
    else:
        error_code = verify_result.get("error", {}).get("code", "Unknown")
        auth_failures = [
            "AuthFailure.SecretIdNotFound",
            "AuthFailure.SignatureFailure",
            "AuthFailure.InvalidSecretId",
        ]
        if error_code in auth_failures:
            log_fail(f"AK/SK 无效: {error_code}")
            log_info("  请检查密钥是否正确: https://console.cloud.tencent.com/cam/capi")
            sys.exit(2)
        elif error_code in ("NetworkError", "HTTPError"):
            log_fail("接口调用失败，请检查网络连接")
            sys.exit(1)
        else:
            log_ok("AK/SK 验证通过（鉴权成功）")
            if not QUIET_MODE:
                log_warn(f"接口返回业务错误: {error_code}（不影响鉴权）")

    # ============== 5. 检查智能顾问开通状态 ==============
    log_section("5. 检查智能顾问开通状态")

    advisor_auth_result = call_api(
        "advisor", "advisor.tencentcloudapi.com",
        "DescribeUserAuthorizationStatus", "2020-07-21",
        {},
        "ap-guangzhou",
    )

    advisor_authorized = False
    if advisor_auth_result.get("success"):
        auth_data = advisor_auth_result.get("data", {})
        advisor_authorized = auth_data.get("AdvisorAuthorization", False)
        share_authorized = auth_data.get("ShareAuthorization", False)
        if advisor_authorized:
            log_ok("智能顾问已开通")
            if share_authorized:
                log_ok("架构图共享协作已开启")
            else:
                log_warn("架构图共享协作未开启（不影响 CloudQ 基本功能）")
        else:
            log_fail("智能顾问未开通")
            if ENABLE_ADVISOR:
                log_info("  正在开通智能顾问...")
                enable_result = call_api(
                    "advisor", "advisor.tencentcloudapi.com",
                    "CreateAdvisorAuthorization", "2020-07-21",
                    {},
                    "ap-guangzhou",
                )
                if enable_result.get("success"):
                    log_ok("智能顾问开通成功！")
                    advisor_authorized = True
                else:
                    err = enable_result.get("error", {})
                    log_fail(f"智能顾问开通失败: {err.get('code', 'Unknown')} - {err.get('message', '未知错误')}")
                    sys.exit(4)
            else:
                log_info("  CloudQ 所有功能均依赖智能顾问服务，必须先开通才能使用")
                log_info("  开通方式：请在对话中同意开通，或运行以下命令：")
                log_info(f"  python3 {SCRIPT_DIR}/check_env.py --enable-advisor")
                sys.exit(4)
    else:
        error_code = advisor_auth_result.get("error", {}).get("code", "Unknown")
        if error_code in ("NetworkError", "HTTPError"):
            log_fail("查询智能顾问开通状态失败，请检查网络连接")
            sys.exit(1)
        else:
            # 权限类错误，AK/SK 可能没有 advisor 权限
            log_warn(f"查询智能顾问开通状态失败: {error_code}")
            log_info("  可能原因：当前 AK/SK 无智能顾问相关权限")
            log_info("  请确保已授予策略: QcloudTAGFullAccess + ReadOnlyAccess + QcloudAdvisorAccessForCloudQ")
            # 不阻断流程，继续检测角色

    # ============== 6. 检查角色配置状态（仅检测，不创建） ==============
    log_section("6. 检查免密登录角色配置")

    role_arn = os.environ.get("TENCENTCLOUD_ROLE_ARN", "")
    role_configured = False

    # 6.1 优先检查环境变量
    if role_arn:
        log_ok("ROLE_ARN 已通过环境变量配置")
        role_configured = True

    # 6.2 检查配置文件
    if not role_configured and CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            saved_arn = config.get("roleArn", "")
            saved_role = config.get("roleName", "")
            if saved_arn:
                log_ok(f"角色已配置（来自配置文件）: {saved_role}")
                role_configured = True
        except (json.JSONDecodeError, IOError):
            pass

    # 6.3 检查 ROLE_NAME 环境变量
    if not role_configured:
        role_name_env = os.environ.get("TENCENTCLOUD_ROLE_NAME", "")
        if role_name_env:
            log_ok(f"ROLE_NAME 已配置: {role_name_env}")
            role_configured = True

    # 6.4 角色未配置 → 检测账号下是否存在可用角色
    if not role_configured:
        log_warn("免密登录角色未配置")
        log_info("")

        # 获取账号 UIN
        uin_result = call_api(
            "sts", "sts.tencentcloudapi.com",
            "GetCallerIdentity", "2018-08-13", {},
        )
        account_uin = str(uin_result.get("data", {}).get("AccountId", ""))

        if not account_uin or account_uin == "None":
            log_fail("无法获取账号 UIN")
            log_info("  需要创建角色用于免密登录，请先检查网络和 AK/SK 权限")
            sys.exit(3)

        log_info(f"  账号 UIN: {account_uin}")

        # 检查 advisor 角色是否已存在
        log_info(f"  检查 {ADVISOR_ROLE_NAME} 角色是否存在...")
        role_check = call_api(
            "cam", "cam.tencentcloudapi.com",
            "GetRole", "2019-01-16",
            {"RoleName": ADVISOR_ROLE_NAME},
        )

        if role_check.get("success"):
            console_login = role_check.get("data", {}).get("ConsoleLogin", 0)
            if console_login == 1:
                # 角色存在且支持控制台登录 → 保存配置
                log_ok(f"检测到已有角色 {ADVISOR_ROLE_NAME}（支持控制台登录），自动配置")
                computed_arn = f"qcs::cam::uin/{account_uin}:roleName/{ADVISOR_ROLE_NAME}"
                role_id = str(role_check.get("data", {}).get("RoleId", ""))
                save_config(account_uin, ADVISOR_ROLE_NAME, computed_arn,
                            auto_created=False, role_id=role_id)
                log_ok(f"配置已保存到 {CONFIG_FILE}")
                role_configured = True
            else:
                log_warn(f"角色 {ADVISOR_ROLE_NAME} 存在但不支持控制台登录")
                log_info("  尝试查找其他支持控制台登录的角色...")
        else:
            log_warn(f"未检测到 {ADVISOR_ROLE_NAME} 角色")
            log_info("  尝试查找其他支持控制台登录的角色...")

        # 6.5 advisor 不可用 → 查询角色列表寻找可用角色
        if not role_configured:
            list_result = list_console_login_roles()
            if list_result.get("success") and list_result.get("roles"):
                found_role = list_result["roles"][0]
                found_name = found_role.get("RoleName", "")
                log_ok(f"检测到可用角色 {found_name}（支持控制台登录），自动配置")
                computed_arn = f"qcs::cam::uin/{account_uin}:roleName/{found_name}"
                role_id = str(found_role.get("RoleId", ""))
                save_config(account_uin, found_name, computed_arn,
                            auto_created=False, role_id=role_id)
                log_ok(f"配置已保存到 {CONFIG_FILE}")
                role_configured = True
            else:
                log_warn("未找到任何支持控制台登录的角色")
                log_info("")
                log_info("  免密登录功能需要一个支持控制台登录的 CAM 角色（可选，不影响 CloudQ 基本功能）")
                log_info(f"  如需启用免密登录，请执行: python3 {SCRIPT_DIR}/scripts/create_role.py")
                # 角色未配置不阻断流程，CloudQ 基本功能仍可用

    # ============== 6.6 确保角色策略完整（为存量角色补充新增策略） ==============
    if role_configured:
        # 获取角色名称（从配置文件或环境变量）
        policy_role_name = ""
        if CONFIG_FILE.exists():
            try:
                config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                policy_role_name = config.get("roleName", "")
            except (json.JSONDecodeError, IOError):
                pass
        if not policy_role_name:
            policy_role_name = os.environ.get("TENCENTCLOUD_ROLE_NAME", ADVISOR_ROLE_NAME)

        policy_warnings = ensure_role_policies(policy_role_name)
        if policy_warnings:
            for w in policy_warnings:
                log_warn(w)
        else:
            log_ok("角色策略检查通过")

    # ============== 7. 验证角色扮演（仅角色已配置时） ==============
    if role_configured:
        log_section("7. 验证角色扮演")

        # 调用 login_url.py 中的逻辑验证
        try:
            scripts_dir = SCRIPT_DIR / "scripts"
            login_url_path = scripts_dir / "login_url.py"
            if not login_url_path.exists():
                login_url_path = SCRIPT_DIR / "login_url.py"

            import subprocess
            test_result = subprocess.run(
                [sys.executable, str(login_url_path),
                 "https://console.cloud.tencent.com/advisor"],
                capture_output=True, text=True, timeout=30,
            )
            try:
                result_data = json.loads(test_result.stdout)
                if result_data.get("success"):
                    log_ok("角色扮演验证通过，免密登录功能正常")
                else:
                    err_msg = result_data.get("error", {}).get("message", "未知错误")
                    log_warn(f"角色扮演验证失败: {err_msg}")
                    log_info("  免密登录功能可能需要等待角色生效（通常几秒内）")
            except json.JSONDecodeError:
                log_warn("角色扮演验证返回格式异常")
        except Exception as e:
            log_warn(f"角色扮演验证异常: {e}")

    # ============== 检测完成 ==============
    log_info("")
    log_info("=== 检测完成 ===")
    if advisor_authorized and role_configured:
        log_ok("环境就绪，所有功能可用（智能顾问已开通 + API 查询 + 免密登录）")
        log_info("")
        log_info(f"  [OK] Python {py_ver.major}.{py_ver.minor} ({platform.system()})")
        log_info("  [OK] AK/SK 密钥验证通过")
        log_info("  [OK] 智能顾问已开通")
        log_info("  [OK] 免密登录角色已配置")
        sys.exit(0)
    elif advisor_authorized and not role_configured:
        log_ok("环境基本就绪（智能顾问已开通，API 查询可用）")
        log_warn("免密登录角色未配置（仅影响免密登录链接生成，不影响 CloudQ 基本功能）")
        log_info("")
        log_info(f"  [OK] Python {py_ver.major}.{py_ver.minor} ({platform.system()})")
        log_info("  [OK] AK/SK 密钥验证通过")
        log_info("  [OK] 智能顾问已开通")
        log_info("  [WARN] 免密登录角色未配置")
        log_info("")
        log_info("  可选：执行角色创建步骤以启用免密登录功能")
        log_info(f"  python3 {SCRIPT_DIR}/scripts/create_role.py")
        sys.exit(0)
    else:
        log_fail("环境检测未通过")
        log_info("")
        log_info("  请根据上方提示完成初始化")
        sys.exit(3)


if __name__ == "__main__":
    main()
