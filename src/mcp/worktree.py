"""任务工作树（task worktree）管理模块。

设计思路：
- 借鉴 Cline / ts2-agent 的 --worktree 模式：为每个任务创建一个独立的 git
  worktree（基于 HEAD 的分离头指针检出），使多任务在各自目录中并行开发，
  互不污染对方的工作区与未提交改动。
- 工作树统一存放在 ~/.ts2/worktrees/<task_id>/<workspace_label> 下：
  * task_id：短随机 ID（默认 5 位十六进制），可用自定义 id，但必须通过
    validate_task_id 黑名单校验，防止路径穿越；
  * workspace_label：仓库根目录名的可打印净化版本，便于人工识别。
- 失败处理：git worktree add 失败时清理本次新建的父目录，避免残留空壳；
  移除工作树时先普通 remove，失败（如存在未提交改动）再降级为 --force。

与 Cline 的对应关系：Cline 生态中"每个任务独立工作区"的隔离方案，
CLI 侧对应 --worktree 参数（git 命令由本模块统一构造执行）。
"""

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

# 短任务 ID 的长度（uuid4 十六进制前缀截取位数）
TASK_ID_LENGTH = 5
# task_id 与已有工作树目录冲突时，最多重新生成的次数
MAX_WORKTREE_RETRIES = 16
# 轻量 git 命令（version/rev-parse/list）的超时时间（秒）
GIT_COMMAND_TIMEOUT = 30
# 较重操作（worktree add/remove）的超时时间（秒），避免大仓库卡死
WORKTREE_OPERATION_TIMEOUT = 120


@dataclass
class CreateWorktreeResult:
    """创建任务工作树的返回结果。

    success=False 时 message 给出失败原因；success=True 时 path / task_id /
    repo_root 均被填充，供调用方使用工作树路径。
    """

    success: bool
    message: str
    path: Optional[str] = None
    task_id: Optional[str] = None
    repo_root: Optional[str] = None


def get_worktrees_home_path() -> str:
    """返回工作树的统一根目录：~/.ts2/worktrees。"""
    return os.path.join(os.path.expanduser("~"), ".ts2", "worktrees")


def check_git_installed() -> bool:
    """探测 git 是否可用（git --version 返回 0 即可用）。

    任何异常（命令缺失/超时/非零退出）都视为未安装，返回 False。
    """
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=GIT_COMMAND_TIMEOUT)
        return result.returncode == 0
    except Exception:
        return False


def get_git_root_path(cwd: str) -> Optional[str]:
    """解析 cwd 所在 git 仓库的根目录绝对路径。

    Returns:
        Optional[str]: 仓库根路径；cwd 不在 git 仓库内或命令失败时返回 None。
    """
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        root = result.stdout.strip()
        return root or None
    except Exception:
        return None


def validate_task_id(task_id: str) -> bool:
    """校验任务 ID 是否安全，防止路径穿越/控制字符注入。

    黑名单：/ 与 \\（路径分隔符）、..（目录回溯）、\\x00（NUL 截断）。
    这些字符一旦进入工作树路径，可能把目录写到 ~/.ts2/worktrees 之外。
    """
    if not task_id:
        return False
    if "/" in task_id or "\\" in task_id or ".." in task_id or "\x00" in task_id:
        return False
    return True


def create_short_task_id() -> str:
    """生成一个短随机任务 ID（uuid4 十六进制前 TASK_ID_LENGTH 位）。"""
    return uuid.uuid4().hex[:TASK_ID_LENGTH]


def get_workspace_label(repo_path: str) -> str:
    """从仓库根路径提取一个可打印的目录名作为工作树标签。

    过滤掉所有不可打印字符（ASCII 32~126 之外），空结果回退为 "workspace"，
    保证生成的目录名在各平台上都合法、可读。
    """
    folder = os.path.basename(repo_path.rstrip("/\\")) or "workspace"
    cleaned = "".join(ch for ch in folder if 32 <= ord(ch) < 127).strip()
    return cleaned or "workspace"


def create_task_worktree(cwd: str, task_id: str = "") -> CreateWorktreeResult:
    """在当前仓库下为任务创建独立 git worktree。

    Args:
        cwd: 所在工作目录（用于定位 git 仓库根目录）。
        task_id: 自定义任务 ID；为空时自动生成短随机 ID。
            与已有工作树目录冲突时会自动重试生成新 ID（最多 MAX_WORKTREE_RETRIES 次）。

    Returns:
        CreateWorktreeResult: 成功时含 worktree 路径 / task_id / repo_root；
            失败时 success=False 且 message 说明原因。

    流程校验顺序：git 可用 -> 在 git 仓库内 -> task_id 安全 -> 目录不冲突。
    """
    # 前置检查 1：git 必须可用，否则 worktree 命令无从谈起
    if not check_git_installed():
        return CreateWorktreeResult(
            success=False,
            message="Git is not installed. --worktree requires git on PATH.",
        )

    # 前置检查 2：cwd 必须位于 git 仓库内
    repo_root = get_git_root_path(cwd)
    if not repo_root:
        return CreateWorktreeResult(
            success=False,
            message=f"Not a git repository: {cwd}. --worktree requires a git repo.",
        )

    tid = task_id.strip() if task_id else create_short_task_id()
    # 前置检查 3：task_id 必须通过黑名单校验，防止目录逃逸
    if not validate_task_id(tid):
        return CreateWorktreeResult(success=False, message=f"Invalid worktree id: {tid}")

    home = get_worktrees_home_path()
    label = get_workspace_label(repo_root)
    worktree_path = os.path.join(home, tid, label)

    # 目标目录已存在（task_id 冲突）时，重新生成短 ID 直到找到空闲目录；
    # 重试次数达到上限则沿用最后一次生成的路径（大概率仍会失败，由后续 git 命令兜底）
    if os.path.exists(worktree_path):
        for _ in range(MAX_WORKTREE_RETRIES):
            tid = create_short_task_id()
            worktree_path = os.path.join(home, tid, label)
            if not os.path.exists(worktree_path):
                break

    parent_dir = os.path.dirname(worktree_path)
    # 记录父目录是否原本就存在：若原本不存在而创建失败，需整体清理避免残留空壳
    parent_dir_existed = os.path.exists(parent_dir)

    try:
        os.makedirs(parent_dir, exist_ok=True)
        # --detach：从 HEAD 检出分离头指针，不占用分支名；HEAD 即当前提交
        result = subprocess.run(
            ["git", "-C", repo_root, "worktree", "add", "--detach", worktree_path, "HEAD"],
            capture_output=True,
            text=True,
            timeout=WORKTREE_OPERATION_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or f"git worktree add failed with code {result.returncode}"
            )
        return CreateWorktreeResult(
            success=True,
            message=f"Worktree created at {worktree_path}",
            path=worktree_path,
            task_id=tid,
            repo_root=repo_root,
        )
    except Exception as exc:
        # 创建失败且父目录是本流程新建的：整体删除，不留半成品目录
        if not parent_dir_existed:
            shutil.rmtree(parent_dir, ignore_errors=True)
        return CreateWorktreeResult(success=False, message=f"Failed to create worktree: {exc}")


def _resolve_worktree_repo(path: str) -> Optional[str]:
    """从 worktree 的 .git 指针文件解析主仓库根。

    git worktree 的 .git 是一个指针文件，内容形如
    "gitdir: <主仓库>/.git/worktrees/<name>"。解析它定位主仓库，
    以便在主仓库上下文中执行 git worktree remove（不能 -C worktree 自身，
    否则移除过程中 .git 指针失效会报 not a git repository）。
    """
    try:
        gitfile = os.path.join(path, ".git")
        with open(gitfile, encoding="utf-8") as f:
            line = f.read().strip()
        if not line.startswith("gitdir:"):
            return None
        gitdir = os.path.normpath(
            os.path.join(path, line[len("gitdir:"):].strip())
        )
        # gitdir 形如 <repo>/.git/worktrees/<name> → 回退两层到 <repo>
        repo = os.path.dirname(os.path.dirname(gitdir))
        return repo or None
    except Exception:
        return None


def remove_worktree(path: str) -> bool:
    """移除指定路径的 git worktree。

    先尝试普通移除；若因存在未提交改动等被 git 拒绝，再降级为 --force 强制移除。
    执行基准：优先从主仓库（由 .git 指针解析）运行；解析失败时回退当前目录。

    Returns:
        bool: 是否移除成功（任一次 git 命令成功即返回 True）。
    """
    repo = _resolve_worktree_repo(path)

    def _run(extra: list) -> subprocess.CompletedProcess:
        if repo:
            return subprocess.run(
                ["git", "-C", repo, "worktree", "remove", *extra, path],
                capture_output=True, text=True,
                timeout=WORKTREE_OPERATION_TIMEOUT,
            )
        return subprocess.run(
            ["git", "worktree", "remove", *extra, path],
            capture_output=True, text=True,
            timeout=WORKTREE_OPERATION_TIMEOUT,
        )

    try:
        result = _run([])
        if result.returncode == 0:
            return True
        # 普通移除失败（通常是有未提交改动）时强制移除
        forced = _run(["--force"])
        return forced.returncode == 0
    except Exception:
        return False


def list_worktrees(cwd: Optional[str] = None) -> List[Dict]:
    """列出仓库的全部 worktree（解析 git worktree list --porcelain 输出）。

    Args:
        cwd: 查询目录；缺省为当前工作目录。

    Returns:
        List[Dict]: 每个 worktree 一条记录，含 path / head / branch /
        detached（如有）；命令失败或不在仓库内时返回空列表。

    解析约定：--porcelain 输出以空行分隔条目，字段以 "key value" 形式出现，
    "detached" 是单独一行。
    """
    base = cwd if cwd else os.getcwd()
    try:
        result = subprocess.run(
            ["git", "-C", base, "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    worktrees: List[Dict] = []
    current: Dict = {}
    for line in result.stdout.splitlines():
        # 空行表示一个 worktree 条目结束
        if not line:
            if current:
                worktrees.append(current)
                current = {}
        elif line.startswith("worktree "):
            current["path"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line == "detached":
            current["detached"] = True
    # 收尾：处理最后一个条目（输出末尾可能没有空行）
    if current:
        worktrees.append(current)
    return worktrees
