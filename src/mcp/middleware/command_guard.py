"""Plan 模式下终端命令的黑名单守卫中间件。

设计思路
--------
Plan 模式本应只允许终端工具执行只读调查命令，但模型（尤其弱模型）常会通过
shell 直接改写文件。本模块把 Cline 的 command-guard.ts（位于
references/cline/sdk/packages/core/src/extensions/tools/command-guard.ts）中
的"轻量黑名单"逻辑复刻为 Python：不解析完整 shell 语法，而是先对命令做轻量
预处理（掩码掉引号、here-doc 主体、转义、注释等"数据"部分，避免误报），再
按 shell 分隔符拆分，逐段比对命令首词与黑名单，同时拒绝输出重定向到非白名单
位置。

对应关系
--------
- BLOCKED_COMMANDS / BLOCKED_SUBCOMMANDS / READ_ONLY_GIT_FORMS / WRAPPERS /
  RESERVED_WORDS 等常量：对应 Cline command-guard.ts 中的同名集合。
- normalize_command_name / mask_non_command_text / check_tokens /
  analyze_command：分别对应 Cline 的 normalizeCommandName / maskNonCommandText /
  checkTokens / findFileEditingCommand。
- CommandGuardMiddleware：对应 Cline 中 createShellTool 在 Plan 模式下对
  run_commands 的拦截行为（命中黑名单即返回工具错误而不是执行命令）。

局限性
------
它不是完整 shell 解释器，无法拦截所有可能的写入（例如 python -c 内打开文件、
引号包裹的 bash -c 字符串），但足以拦截模型从 shell 改文件的常见写法，且
黑名单条目易于扩展。
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .base import AgentMiddleware, MiddlewareAction, MiddlewareContext, MiddlewareResult

# 直接创建/修改/删除文件的命令黑名单（对应 Cline 的 BLOCKED_COMMANDS）：
# 前半部分为 POSIX 命令，后半部分为 Windows/PowerShell 命令及其无歧义别名。
BLOCKED_COMMANDS: Set[str] = {
    "rm",
    "rmdir",
    "unlink",
    "mv",
    "cp",
    "dd",
    "touch",
    "mkdir",
    "ln",
    "link",
    "chmod",
    "chown",
    "chgrp",
    "truncate",
    "shred",
    "install",
    "patch",
    "rsync",
    "mkfifo",
    "mknod",
    "del",
    "erase",
    "move",
    "ren",
    "rename",
    "md",
    "rd",
    "mklink",
    "copy",
    "xcopy",
    "robocopy",
    "new-item",
    "ni",
    "remove-item",
    "move-item",
    "copy-item",
    "rename-item",
    "set-content",
    "add-content",
    "clear-content",
    "out-file",
    "mi",
    "ri",
    "cpi",
    "rni",
    "ac",
    "clc",
}

# git 中会改变仓库状态或工作区的子命令（对应 Cline 的 GIT_SUBCOMMANDS）。
GIT_SUBCOMMANDS: Set[str] = {
    "add",
    "am",
    "apply",
    "checkout",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "init",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "submodule",
    "switch",
    "worktree",
}

# Node 生态包管理器（npm/pnpm/yarn/bun）中会改动依赖或发布产物的子命令。
NODE_PM_SUBCOMMANDS: Set[str] = {
    "install",
    "i",
    "ci",
    "add",
    "remove",
    "rm",
    "uninstall",
    "unlink",
    "link",
    "update",
    "up",
    "upgrade",
    "dedupe",
    "prune",
    "publish",
}

# pip 系列（pip/pip3/pipx/uv）中会改动环境的子命令。
PIP_SUBCOMMANDS: Set[str] = {"install", "uninstall", "add", "remove"}

# cargo（Rust 包管理器）中会改动项目或环境的子命令。
CARGO_SUBCOMMANDS: Set[str] = {
    "add",
    "remove",
    "rm",
    "install",
    "uninstall",
    "update",
    "new",
    "init",
    "publish",
}

# gem（Ruby 包）与 composer（PHP 包）中会改动本地环境/依赖的子命令。
GEM_SUBCOMMANDS: Set[str] = {"install", "uninstall", "update", "cleanup"}

COMPOSER_SUBCOMMANDS: Set[str] = {"install", "require", "remove", "update"}

# go 工具链与 dotnet 中会拉取/安装或改动项目引用的子命令。
GO_SUBCOMMANDS: Set[str] = {"install", "get"}

DOTNET_SUBCOMMANDS: Set[str] = {"add", "remove"}

# Windows 的 winget 与 .NET 的 nuget 中会改动系统的子命令。
WINGET_SUBCOMMANDS: Set[str] = {"install", "uninstall", "upgrade"}

NUGET_SUBCOMMANDS: Set[str] = {"install", "update", "delete", "push"}

# 系统级包管理器（apt/apt-get/dnf/yum/apk/brew/snap）中会改动系统的子命令。
SYSTEM_PM_SUBCOMMANDS: Set[str] = {
    "install",
    "reinstall",
    "remove",
    "purge",
    "uninstall",
    "upgrade",
    "autoremove",
    "add",
    "del",
}

# 按"命令名 -> 其会改状态的子命令集合"组织的总表，供 check_tokens 查表。
BLOCKED_SUBCOMMANDS: Dict[str, Set[str]] = {
    "git": GIT_SUBCOMMANDS,
    "npm": NODE_PM_SUBCOMMANDS,
    "pnpm": NODE_PM_SUBCOMMANDS,
    "yarn": NODE_PM_SUBCOMMANDS,
    "bun": NODE_PM_SUBCOMMANDS,
    "pip": PIP_SUBCOMMANDS,
    "pip3": PIP_SUBCOMMANDS,
    "pipx": PIP_SUBCOMMANDS,
    "uv": PIP_SUBCOMMANDS,
    "cargo": CARGO_SUBCOMMANDS,
    "apt": SYSTEM_PM_SUBCOMMANDS,
    "apt-get": SYSTEM_PM_SUBCOMMANDS,
    "dnf": SYSTEM_PM_SUBCOMMANDS,
    "yum": SYSTEM_PM_SUBCOMMANDS,
    "apk": SYSTEM_PM_SUBCOMMANDS,
    "brew": SYSTEM_PM_SUBCOMMANDS,
    "snap": SYSTEM_PM_SUBCOMMANDS,
    "gem": GEM_SUBCOMMANDS,
    "composer": COMPOSER_SUBCOMMANDS,
    "go": GO_SUBCOMMANDS,
    "dotnet": DOTNET_SUBCOMMANDS,
    "winget": WINGET_SUBCOMMANDS,
    "nuget": NUGET_SUBCOMMANDS,
}

# 部分 git 子命令本身会改状态，但存在只读形态：`git stash list` 只查看、
# `git stash` 才真正暂存改动，判定时需结合后继参数放行。
READ_ONLY_GIT_FORMS: Dict[str, Set[str]] = {
    "stash": {"list", "show"},
    "worktree": {"list"},
    "submodule": {"status", "summary"},
}

# 前缀包装命令：判定前需跳过它们（连同其选项/参数）以定位真正执行的命令词。
WRAPPERS: Set[str] = {
    "sudo",
    "doas",
    "env",
    "command",
    "builtin",
    "nohup",
    "time",
    "nice",
    "stdbuf",
    "timeout",
    "xargs",
}

# shell 保留字：可出现在命令词之前，比对时需一并跳过。
RESERVED_WORDS: Set[str] = {
    "if",
    "then",
    "else",
    "elif",
    "fi",
    "while",
    "until",
    "do",
    "done",
    "for",
    "case",
    "esac",
    "!",
    "{",
    "}",
}

# 会被当作终端命令执行的工具名集合；仅这些工具的参数才需要做黑名单检查。
TERMINAL_TOOLS: Set[str] = {
    "bash",
    "shell",
    "execute",
    "exec",
    "sandbox_execute",
    "cli",
    "terminal",
    "run_command",
}

# 终端工具入参中可能承载命令文本的键名，按优先级依次探测。
COMMAND_KEYS: tuple = ("command", "cmd", "script", "input")

# 环境变量赋值前缀（FOO=bar / FOO+=bar）：出现在命令词之前时需跳过。
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")

# 文本工具的就地编辑旗标：-i、-i.bak、-iSUFFIX。选项簇必须以小写 i 收尾
# （可选后缀），避免误伤带取值的选项，如 perl -Ilib。
IN_PLACE_FLAG = re.compile(r"^-[A-Za-z]*i(\..*)?$")

# 输出重定向：>、>>、&>、>>& 后跟随的目标，捕获组 (1) 取出目标本身。
REDIRECT_RE = re.compile(r"(?:^|[^<>])(?:>{1,2}|&>{1,2})\s*([^\s;&|<>()]+)")

# here-doc 起始标记：<<DELIM / <<-DELIM / <<'DELIM' / <<"DELIM"。其后的主体
# 内容是数据而非命令，需要从扫描文本中剔除。
HEREDOC_RE = re.compile(r'(?<![<])<<-?\s*(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z0-9_./-]+))')

# 单/双引号包裹的整段文本：内部是字面数据，不得参与黑名单匹配。
QUOTES_RE = re.compile(r'"[^"]*"|\'[^\']*\'', re.DOTALL)

# shell 注释：# 起头到行尾属于注释文本，匹配后替换为空格以免误报。
COMMENT_RE = re.compile(r"(?:^|\s)#.*$", re.MULTILINE)

# 命令分隔符：换行、分号、管道、子 shell 与命令替换，据此把命令拆成独立段。
SPLIT_RE = re.compile(r"[\n;|&()`]+")

# 文件描述符复制目标：如 2>&1、>&2、1>&3，属于重定向白名单。
FD_DUP_RE = re.compile(r"^&?\d+$")

# 不会把数据持久化到工作区文件的 sink：/dev/null 等设备与 Windows 的 nul。
ALLOWED_SINK_RE = re.compile(r"^(\/dev\/(null|stdout|stderr|tty)|nul:?)$", re.IGNORECASE)

# Windows cmd 的临时目录写法：%TEMP%、%tmp%。
WINDOWS_TEMP_RE = re.compile(r"^%te?mp%", re.IGNORECASE)

# PowerShell 的临时目录写法：$env:TEMP、$env:tmp。
PS_TEMP_RE = re.compile(r"^\$env:te?mp", re.IGNORECASE)


@dataclass
class CommandGuardResult:
    """一次命令黑名单检查的结论。

    字段
    ----
    blocked: 是否命中黑名单（命令疑似会修改文件或环境）。
    reason: 命中原因的人类可读描述；未命中时为空字符串。
    matched_command: 实际被判定为危险的命令片段，用于提示用户。
    """
    blocked: bool = False
    reason: str = ""
    matched_command: str = ""


def is_allowed_redirect_target(raw_target: str) -> bool:
    """判断输出重定向的目标是否为"安全落点"。

    安全目标包括：/dev/null、/dev/stdout、/dev/stderr、/dev/tty、Windows 的
    nul，以及各类临时目录（/tmp、/var/tmp、$TMPDIR、%TEMP%、$env:TEMP）。
    临时目录被放行是因为终端工具的说明文档指引模型把长输出捕获到临时文件，
    这些位置不会污染工作区。

    参数
    ----
    raw_target: 重定向目标原文（可能带引号）。

    返回
    ----
    目标安全返回 True；目标含 `..` 段时直接返回 False，防止 /tmp/../工作区
    这类路径借临时前缀"绕道"写回工作区。

    对应 Cline 的 isAllowedRedirectTarget。
    """
    target = raw_target.replace('"', "").replace("'", "")
    # 设备 sink 与 Windows nul 恒安全（不会落到工作区文件）。
    if ALLOWED_SINK_RE.match(target):
        return True
    # 只要含 `..` 一律拒绝：临时目录前缀也可能被拼回工作区路径。
    if ".." in target:
        return False
    # 仅放行各类临时目录（POSIX 与 Windows 双形态）。
    return (
        target.startswith("/tmp/")
        or target.startswith("/var/tmp/")
        or target.startswith("$TMPDIR")
        or target.startswith("${TMPDIR")
        or bool(WINDOWS_TEMP_RE.match(target))
        or bool(PS_TEMP_RE.match(target))
    )


def normalize_command_name(word: str) -> str:
    """把命令词规范化为"裸文件名"以便查表。

    - 去掉引号（引号包裹的命令名与裸命令名等价）；
    - 取路径最后一段（/usr/bin/git 归约为 git）；
    - 转小写并剥掉 Windows 的 .exe 后缀。

    参数
    ----
    word: 原始命令词。

    返回
    ----
    规范化后的命令名。

    对应 Cline 的 normalizeCommandName。
    """
    base = word.replace('"', "").replace("'", "")
    base = re.split(r"[/\\]", base)[-1] or word
    return base.lower().replace(".exe", "")


def mask_non_command_text(command: str) -> str:
    """把命令串中"数据而非命令"的部分掩码掉，避免黑名单误报。

    掩码对象包括：here-doc 主体（整体丢弃）、$((...)) 算术展开、反斜杠转义、
    引号内的整段文本、以及 # 注释。经掩码后，`echo "rm -rf /"` 中的 rm -rf /
    只是引号内的字面数据，不会触发黑名单。

    参数
    ----
    command: 原始命令串。

    返回
    ----
    掩码后的命令串，仅保留真正会被 shell 当作命令或重定向解析的部分。

    对应 Cline 的 maskNonCommandText。
    """
    lines = command.split("\n")
    kept: List[str] = []
    heredoc_delimiter: Optional[str] = None
    for line in lines:
        # 处于 here-doc 主体内：整行丢弃，直到出现分隔符（允许行首制表符）为止。
        if heredoc_delimiter is not None:
            if re.sub(r"^\t+", "", line) == heredoc_delimiter:
                heredoc_delimiter = None
            continue
        kept.append(line)
        # 本行出现 here-doc 起始标记：记录分隔符，其后各行进入"跳过"状态。
        heredoc_match = HEREDOC_RE.search(line)
        if heredoc_match:
            heredoc_delimiter = heredoc_match.group(1) or heredoc_match.group(2) or heredoc_match.group(3)
    text = "\n".join(kept)
    # $((...)) 算术展开里是表达式/比较（如 $((3 > 2))），不是命令或重定向。
    text = re.sub(r"\$\(\([\s\S]*?\)\)", "_", text)
    # 反斜杠转义的字符是字面文本（如 rm\ 不是命令名）。
    text = re.sub(r"\\.", "_", text)
    # 引号内的内容是字面数据：把其中的分隔符/重定向/命令符号全部替换为 "_"；
    # 空白也被掩码，保证引号段始终粘合成单一 token，不会拆出伪命令词。
    text = QUOTES_RE.sub(
        lambda m: re.sub(r"[\s<>|;&$()`#\\]", "_", m.group(0)),
        text,
    )
    # 注释替换为空格（保留换行以维持行结构，便于后续按行拆分）。
    text = COMMENT_RE.sub(" ", text)
    return text


def check_tokens(tokens: List[str]) -> Optional[str]:
    """检查一段命令的 token 列表（命令词 + 参数）是否命中黑名单。

    判定顺序（自上而下、命中即返回）：
    1. 跳过开头的前置内容：环境变量赋值与 shell 保留字；
    2. 跳过包装命令（sudo/env/xargs/...）及其选项参数，定位真正的命令词；
    3. tee：仅当其文件参数不在安全落点时才拦截（`| tee /tmp/x.log` 是官方推荐
       的输出捕获方式）；
    4. 命令名命中 BLOCKED_COMMANDS 直接拦截；
    5. 命令名在 BLOCKED_SUBCOMMANDS 中：解析子命令并判定（git 特殊放行
       --help/-h 与只读形态，如 stash list / worktree list）；
    6. python -m pip 形态按 pip 处理；
    7. sed/perl/awk/sort 的就地编辑旗标、curl/wget 的写文件参数、find 的
       -delete 与 -exec 嵌套命令分别处理。

    参数
    ----
    tokens: 命令切分后的 token 列表（不含重定向目标）。

    返回
    ----
    命中黑名单时返回其人类可读描述（如 "`rm`"、"`git commit`"），否则返回 None。

    对应 Cline 的 checkTokens。
    """
    index = 0
    # 1. 跳过开头的环境变量赋值（FOO=bar）与 shell 保留字（if、{ 等）。
    while index < len(tokens) and (
        ENV_ASSIGNMENT.match(tokens[index]) or tokens[index] in RESERVED_WORDS
    ):
        index += 1
    # 2. 跳过包装命令及其选项：选项可能带值（timeout 30、env FOO=bar、xargs {}）。
    while index < len(tokens) and normalize_command_name(tokens[index]) in WRAPPERS:
        index += 1
        while index < len(tokens) and (
            tokens[index].startswith("-")
            or tokens[index] == "{}"
            or bool(ENV_ASSIGNMENT.match(tokens[index]))
            or bool(re.match(r"^\d+[smhd]?$", tokens[index]))
        ):
            index += 1
    # 全部被跳过（例如只剩 `sudo`）：没有可判定的命令词，放行。
    if index >= len(tokens):
        return None

    name = normalize_command_name(tokens[index])
    args = tokens[index + 1:]

    # 3. tee：`| tee /tmp/log` 是文档化的输出捕获方式，只有写到非临时文件才拦截。
    if name == "tee":
        file_args = [arg for arg in args if not arg.startswith("-")]
        if any(not is_allowed_redirect_target(arg) for arg in file_args):
            return "`tee`"
        return None

    # 4. 命中直接改文件的命令黑名单。
    if name in BLOCKED_COMMANDS:
        return f"`{name}`"

    # 5. 带子命令的包管理/版本控制工具查表。
    subcommands = BLOCKED_SUBCOMMANDS.get(name)
    if subcommands:
        # git 的 --help / -h 只输出帮助，不改变状态。
        if name == "git" and any(arg in ("--help", "-h") for arg in args):
            return None
        # 第一个非选项参数即子命令；`git -c k=v` / `git -C dir` 的选项带取值，
        # 需多跳过一个参数。
        cursor = 0
        while cursor < len(args) and args[cursor].startswith("-"):
            cursor += 2 if (name == "git" and re.match(r"^-[cC]$", args[cursor])) else 1
        subcommand = args[cursor].lower() if cursor < len(args) else ""
        if subcommand and subcommand in subcommands:
            next_arg = args[cursor + 1].lower() if cursor + 1 < len(args) else None
            # git 的只读形态放行：`git stash list`、`git worktree list`、
            # `git submodule status` 只查看不修改。
            if (
                name == "git"
                and next_arg is not None
                and next_arg in READ_ONLY_GIT_FORMS.get(subcommand, set())
            ):
                return None
            return f"`{name} {subcommand}`"
        # 经典 yarn 不带子命令时等价于 install，一并拦截。
        if name == "yarn" and len(args) == 0:
            return "`yarn` (install)"
        return None

    # 6. `python -m pip install ...` 本质是 pip，按 pip 子命令判定。
    if re.match(r"^python[\d.]*$", name):
        if "-m" in args:
            module_index = args.index("-m")
            module = args[module_index + 1].lower() if module_index + 1 < len(args) else None
            if module in ("pip", "pip3"):
                # -m 之后第一个非选项参数即 pip 子命令。
                sub = next(
                    (arg for arg in args[module_index + 2:] if not arg.startswith("-")),
                    None,
                )
                if sub and sub.lower() in PIP_SUBCOMMANDS:
                    return f"`pip {sub.lower()}`"
        return None

    # 7. sed/gsed 的就地编辑：-i、-i.bak、--in-place。
    if name in ("sed", "gsed") and any(
        IN_PLACE_FLAG.match(arg) or arg.startswith("--in-place") for arg in args
    ):
        return "`sed -i` (in-place edit)"

    # perl 的就地编辑：-i / -i.bak（IN_PLACE_FLAG 要求选项簇以小写 i 收尾，
    # 避免误伤带取值的 -Ilib）。
    if name == "perl" and any(IN_PLACE_FLAG.match(arg) for arg in args):
        return "`perl -i` (in-place edit)"

    # awk 系列（awk/gawk/nawk/mawk）的 `-i inplace` 就地编辑形态。
    if re.match(r"^[gnm]?awk$", name):
        uses_inplace = False
        for arg_index, arg in enumerate(args):
            # `-i inplace` 与 `--include inplace`：i/include 与下一参数搭配。
            if (arg in ("-i", "--include") and
                    arg_index + 1 < len(args) and args[arg_index + 1].startswith("inplace")):
                uses_inplace = True
            # `-iinplace` 紧凑写法。
            elif arg.startswith("-i") and arg[2:].startswith("inplace"):
                uses_inplace = True
            # `--include=inplace` 等号写法。
            elif arg.startswith("--include=inplace"):
                uses_inplace = True
        if uses_inplace:
            return "`awk -i inplace` (in-place edit)"
        return None

    # sort -o / --output 会把结果写回文件。
    if name == "sort" and any(
        arg.startswith("-o") or arg.startswith("--output") for arg in args
    ):
        return "`sort -o` (writes a file)"

    # curl 的 -o/-O/--output/--remote-name 会把响应写入文件。
    if name == "curl":
        writes_file = any(
            (not arg.startswith("--") and bool(re.match(r"^-[A-Za-z]*[oO]", arg)))
            or arg.startswith("--output")
            or arg.startswith("--remote-name")
            for arg in args
        )
        return "`curl -o` (writes a file)" if writes_file else None

    # wget 默认下载到文件；--spider / `-O -` / `--output-document=-` 为只读放行。
    if name == "wget":
        read_only = any(
            arg == "--spider"
            or bool(re.match(r"^-[A-Za-z]*O-$", arg))
            or arg == "--output-document=-"
            or (arg == "-O" and arg_index + 1 < len(args) and args[arg_index + 1] == "-")
            for arg_index, arg in enumerate(args)
        )
        return None if read_only else "`wget` (downloads files)"

    # find：-delete 直接删除；-exec/-execdir/-ok/-okdir 内嵌的命令递归判定。
    if name == "find":
        if "-delete" in args:
            return "`find -delete`"
        for arg_index, arg in enumerate(args):
            if arg not in ("-exec", "-execdir", "-ok", "-okdir"):
                continue
            # 收集 -exec 到 `;`/`+` 之间的参数，作为一条独立命令递归检查。
            tail: List[str] = []
            cursor = arg_index + 1
            while cursor < len(args) and args[cursor] not in (";", "+"):
                tail.append(args[cursor])
                cursor += 1
            nested = check_tokens(tail)
            if nested:
                return nested
        return None

    # 未命中任何规则：视为只读命令。
    return None


def analyze_command(command: str) -> CommandGuardResult:
    """对一条完整命令串做黑名单扫描，返回检查结论。

    扫描顺序：
    1. 先做掩码预处理（mask_non_command_text）；
    2. 用 REDIRECT_RE 检查输出重定向，非安全目标直接拦截；
    3. 用 SPLIT_RE 把命令按分隔符拆成简单命令段，逐段调用 check_tokens。

    参数
    ----
    command: 模型即将执行的命令串；非字符串或空白时直接返回"不拦截"。

    返回
    ----
    CommandGuardResult：blocked 为 True 时，reason/matched_command 记录
    第一个被拦截的构造。

    对应 Cline 的 findFileEditingCommand。
    """
    # 结构化参数或空命令：无需检查。
    if not isinstance(command, str) or not command.strip():
        return CommandGuardResult()
    masked = mask_non_command_text(command)
    # 输出重定向检查：>、>>、&> 指向非白名单目标即拦截；
    # fd 复制（2>&1）与安全落点（/dev/null、临时目录）放行。
    for match in REDIRECT_RE.finditer(masked):
        target = match.group(1)
        if FD_DUP_RE.match(target) or is_allowed_redirect_target(target):
            continue
        return CommandGuardResult(
            blocked=True,
            reason=f"输出重定向 (`> {target}`)",
            matched_command=f"> {target}",
        )
    # 按分隔符拆分成简单命令段，逐段检查命令词。
    for segment in SPLIT_RE.split(masked):
        blocked = check_tokens([token for token in segment.split()])
        if blocked:
            return CommandGuardResult(blocked=True, reason=blocked, matched_command=blocked)
    return CommandGuardResult()


class CommandGuardMiddleware(AgentMiddleware):
    """把 command_guard 的静态分析接入中间件链的适配器。

    设计意图
    --------
    仅当处于 Plan 模式且工具属于 TERMINAL_TOOLS 时才做拦截：先用
    _is_plan_mode 判断模式，再用 _extract_command 取出命令文本，最后交给
    analyze_command 分析；命中黑名单时返回 STOP，阻止工具真正执行。
    对应 Cline 中 createShellTool 在 Plan 模式下对 run_commands 返回工具错误
    的拦截行为。

    模式判定优先级（高到低）：set_mode 显式设置 > tool_args 里的 mode 字段 >
    MiddlewareContext.extra 里的 mode 字段 > 外部注入的 mode_getter 回调。
    """
    name = "command_guard"
    order = 10

    def __init__(self, mode_getter: Optional[Any] = None):
        """初始化命令守卫中间件。

        参数
        ----
        mode_getter: 可选回调，返回当前模式字符串（如 "plan"/"act"）；
        在 set_mode 与上下文均未提供模式时兜底使用。
        """
        super().__init__()
        self._mode_getter = mode_getter
        self._mode: Optional[str] = None

    def set_mode(self, mode: str) -> None:
        """显式设定模式（最高优先级），供外部在运行时切换。

        参数
        ----
        mode: 模式名，内部统一转为小写后与 "plan" 比较。
        """
        self._mode = str(mode).lower()

    def _is_plan_mode(self, tool_args: Dict[str, Any], context: Optional[MiddlewareContext]) -> bool:
        """按优先级判定当前是否处于 Plan 模式。

        判定顺序（命中即返回）：
        1. self._mode：set_mode 显式设置的值优先级最高；
        2. tool_args["mode"]：工具参数内携带的模式；
        3. context.extra["mode"]：中间件上下文附加字段里的模式；
        4. self._mode_getter()：外部注入的取值回调（抛异常时按非 Plan 处理）。

        参数
        ----
        tool_args: 本次工具调用的参数。
        context: 中间件上下文，可能为 None。

        返回
        ----
        处于 Plan 模式返回 True，否则 False。
        """
        # 1. set_mode 显式设置优先。
        if self._mode is not None:
            return self._mode == "plan"
        # 2. 工具参数里的 mode 字段。
        if tool_args:
            mode = tool_args.get("mode")
            if mode:
                return str(mode).lower() == "plan"
        # 3. 上下文附加字段里的 mode 字段。
        if context is not None and context.extra:
            mode = context.extra.get("mode")
            if mode:
                return str(mode).lower() == "plan"
        # 4. 外部回调兜底；回调抛异常时按"非 Plan"放行，避免误伤。
        if self._mode_getter is not None:
            try:
                return str(self._mode_getter()).lower() == "plan"
            except Exception:
                return False
        return False

    def _extract_command(self, tool_args: Dict[str, Any]) -> Optional[str]:
        """从工具参数中提取命令文本。

        按 COMMAND_KEYS 的键顺序（command/cmd/script/input）依次探测，
        取第一个字符串类型的值；参数不是字典或没有字符串值时返回 None。

        参数
        ----
        tool_args: 本次工具调用的参数字典。

        返回
        ----
        找到的命令字符串；否则 None。
        """
        if not isinstance(tool_args, dict):
            return None
        for key in COMMAND_KEYS:
            value = tool_args.get(key)
            if isinstance(value, str):
                return value
        return None

    def before_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: MiddlewareContext,
    ) -> MiddlewareResult:
        """工具执行前的拦截入口（AgentMiddleware.before_tool 钩子）。

        逻辑：非 Plan 模式直接放行 → 非终端工具直接放行 → 取不到命令文本
        直接放行 → analyze_command 分析，命中黑名单则 STOP 并附上中文原因，
        否则放行。

        参数
        ----
        tool_name: 即将执行的工具名。
        tool_args: 工具参数。
        context: 中间件上下文。

        返回
        ----
        MiddlewareResult：拦截时 action 为 STOP，reason 说明被禁命令与原因；
        否则默认 CONTINUE 放行。
        """
        # 非 Plan 模式不启用守卫。
        if not self._is_plan_mode(tool_args, context):
            return MiddlewareResult()
        # 只检查会被当作终端命令执行的工具。
        if tool_name not in TERMINAL_TOOLS:
            return MiddlewareResult()
        command = self._extract_command(tool_args)
        # 无命令文本或空白命令无需检查。
        if not command or not command.strip():
            return MiddlewareResult()
        result = analyze_command(command)
        if result.blocked:
            # 命中黑名单：STOP 阻止执行，并把原命令写入 metadata 便于排查。
            return MiddlewareResult(
                action=MiddlewareAction.STOP,
                reason=f"Plan 模式禁止：{result.reason}（{result.matched_command}）",
                metadata={"blocked_command": command},
            )
        return MiddlewareResult()
