from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...tools import Tool

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
AGENTS_DIR = Path(__file__).resolve().parent / "agents"
SCRIPTS_DIR = Path(__file__).resolve().parent / "lib" / "scripts"


def _find_lean4_mcp() -> Optional[str]:
    path = shutil.which("lean4-mcp-proxy")
    if path:
        return path
    for candidate in [
        os.path.expanduser("~/.cargo/bin/lean4-mcp-proxy"),
        "/usr/local/bin/lean4-mcp-proxy",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_lean() -> Optional[str]:
    return shutil.which("lean")


def _find_lake() -> Optional[str]:
    return shutil.which("lake")


def _run_lean4_mcp(*args: str, timeout: int = 60, stdin_data: Optional[str] = None) -> Dict[str, Any]:
    proxy = _find_lean4_mcp()
    if proxy is None:
        return {"error": "lean4-mcp-proxy not found"}
    cmd = [proxy] + list(args)
    env = os.environ.copy()
    if "LAKE_PROJECT" not in env:
        env["LAKE_PROJECT"] = os.getenv("LAKE_PROJECT", "")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=env, input=stdin_data)
        if result.returncode != 0:
            return {"error": result.stderr.strip() or result.stdout.strip(), "returncode": result.returncode}
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"error": f"lean4-mcp-proxy timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _run_lean(code: str, timeout: int = 30) -> Dict[str, Any]:
    lean = _find_lean()
    if lean is None:
        return {"error": "lean not found on PATH"}
    import tempfile
    with tempfile.TemporaryDirectory(prefix="lean4_") as tmp:
        path = Path(tmp) / "check.lean"
        path.write_text(code, encoding="utf-8")
        try:
            result = subprocess.run(
                [lean, str(path)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                cwd=tmp,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"lean check timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}


def _check_lean4_available() -> bool:
    return _find_lean4_mcp() is not None or _find_lean() is not None


def _load_agent_prompt(agent_name: str) -> str:
    if not AGENTS_DIR.exists():
        return ""
    agent_path = AGENTS_DIR / f"{agent_name}.md"
    if agent_path.exists():
        return agent_path.read_text(encoding="utf-8")
    return ""


def _inject_skill_context() -> str:
    skill_path = SKILLS_DIR / "lean4" / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return ""


class Lean4CheckTool(Tool):
    name = "lean4_check"
    description = "使用 Lean 4 编译器检查代码是否通过类型检查"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Lean 4 代码"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
        },
        "required": ["code"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "check", "compile", "typecheck", "proof"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        code = kwargs.get("code", "")
        timeout = kwargs.get("timeout", 30)
        if not code.strip():
            return json.dumps({"error": "code is required"}, ensure_ascii=False)
        result = _run_lean(code, timeout=timeout)
        return json.dumps(result, ensure_ascii=False)


class Lean4OpenFileTool(Tool):
    name = "lean4_open_file"
    description = "通过 lean4-mcp-proxy 打开 Lean 文件（自动检测 Lake workspace）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Lean 文件路径"},
        },
        "required": ["path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "open", "file", "workspace"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "").strip()
        if not path:
            return json.dumps({"error": "path is required"}, ensure_ascii=False)
        if _find_lean4_mcp() is None:
            return json.dumps({"error": "lean4-mcp-proxy not available"}, ensure_ascii=False)
        result = _run_lean4_mcp("open_file", "--path", path, timeout=30)
        return json.dumps(result, ensure_ascii=False)


class Lean4GetDiagnosticsTool(Tool):
    name = "lean4_get_diagnostics"
    description = "获取 Lean 文件的编译诊断信息（错误/警告）"
    parameters = {
        "type": "object",
        "properties": {
            "uri": {"type": "string", "description": "文档 URI"},
        },
        "required": ["uri"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "diagnostics", "errors", "warnings"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        uri = kwargs.get("uri", "").strip()
        if not uri:
            return json.dumps({"error": "uri is required"}, ensure_ascii=False)
        if _find_lean4_mcp() is None:
            return json.dumps({"error": "lean4-mcp-proxy not available"}, ensure_ascii=False)
        result = _run_lean4_mcp("get_diagnostics", "--uri", uri, timeout=60)
        return json.dumps(result, ensure_ascii=False)


class Lean4GetGoalStateTool(Tool):
    name = "lean4_get_goal_state"
    description = "查询 Lean 4 tactic proof 在指定位置的目标状态"
    parameters = {
        "type": "object",
        "properties": {
            "uri": {"type": "string", "description": "文档 URI"},
            "line": {"type": "integer", "description": "行号（从0开始）", "default": 0},
            "character": {"type": "integer", "description": "列号（从0开始）", "default": 0},
        },
        "required": ["uri"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "goal", "proof", "tactic", "state"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        uri = kwargs.get("uri", "").strip()
        if not uri:
            return json.dumps({"error": "uri is required"}, ensure_ascii=False)
        if _find_lean4_mcp() is None:
            return json.dumps({"error": "lean4-mcp-proxy not available"}, ensure_ascii=False)
        line = kwargs.get("line", 0)
        character = kwargs.get("character", 0)
        result = _run_lean4_mcp("get_goal_state", "--uri", uri, "--line", str(line), "--character", str(character), timeout=30)
        return json.dumps(result, ensure_ascii=False)


class Lean4LakeBuildTool(Tool):
    name = "lean4_lake_build"
    description = "在 Lake 项目目录中执行 lake build"
    parameters = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string", "description": "Lake 项目目录路径"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 300},
        },
        "required": ["project_dir"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "lake", "build", "project"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        project_dir = kwargs.get("project_dir", "").strip()
        timeout = kwargs.get("timeout", 300)
        if not project_dir:
            return json.dumps({"error": "project_dir is required"}, ensure_ascii=False)
        lake = _find_lake()
        if lake is None:
            return json.dumps({"error": "lake not found on PATH"}, ensure_ascii=False)
        try:
            result = subprocess.run(
                [lake, "build"],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                cwd=project_dir,
            )
            return json.dumps({
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0,
            }, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"lake build timed out after {timeout}s"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


class Lean4ProveTool(Tool):
    name = "lean4_prove"
    description = "引导式定理证明：逐步填充 sorry、检查目标状态、编译验证"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Lean 文件路径"},
            "theorem_name": {"type": "string", "description": "要证明的定理名称（可选，默认尝试所有 sorries）"},
            "scope": {"type": "string", "description": "证明范围: one, dependencies, all", "default": "all"},
            "max_cycles": {"type": "integer", "description": "最大证明周期数", "default": 10},
        },
        "required": ["file_path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "prove", "sorry", "theorem", "proof"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path", "").strip()
        theorem_name = kwargs.get("theorem_name", "")
        scope = kwargs.get("scope", "all")
        max_cycles = kwargs.get("max_cycles", 10)

        if not file_path:
            return json.dumps({"error": "file_path is required"}, ensure_ascii=False)

        skill_ctx = _inject_skill_context()
        return json.dumps({
            "file_path": file_path,
            "theorem_name": theorem_name,
            "scope": scope,
            "max_cycles": max_cycles,
            "status": "ready",
            "skill_context_length": len(skill_ctx),
            "instruction": "使用 lean4_check 编译检查、lean4_get_goal_state 查询目标状态、lean4_get_diagnostics 获取错误，逐步填充 sorry。每次修改后用 lean4_check 验证。",
        }, ensure_ascii=False)


class Lean4FormalizeTool(Tool):
    name = "lean4_formalize"
    description = "非正式数学描述转为 Lean 4 形式化代码（draft + prove）"
    parameters = {
        "type": "object",
        "properties": {
            "informal_spec": {"type": "string", "description": "非正式数学描述（自然语言）"},
            "mode": {"type": "string", "description": "模式: interactive, autonomous", "default": "interactive"},
            "target_file": {"type": "string", "description": "目标 .lean 文件路径"},
        },
        "required": ["informal_spec"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "formalize", "math", "latex", "natural language"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        informal_spec = kwargs.get("informal_spec", "")
        mode = kwargs.get("mode", "interactive")
        target_file = kwargs.get("target_file", "")

        if not informal_spec.strip():
            return json.dumps({"error": "informal_spec is required"}, ensure_ascii=False)

        skill_ctx = _inject_skill_context()

        return json.dumps({
            "informal_spec": informal_spec[:2000],
            "mode": mode,
            "target_file": target_file,
            "status": "draft_ready",
            "skill_context_length": len(skill_ctx),
            "instruction": f"阶段1: 将非正式描述转为 Lean 4 声明骨架 (theorem/lemma + 类型签名)。阶段2: 使用 lean4_prove {mode} 模式填充证明。每个阶段后用 lean4_check 验证。",
        }, ensure_ascii=False)


class Lean4GolfTool(Tool):
    name = "lean4_golf"
    description = "优化 Lean 4 证明：精简长度、提高直接性、改善可读性，不改变语义"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Lean 文件路径"},
            "search_mode": {"type": "string", "description": "搜索模式: off, quick, full", "default": "quick"},
            "max_hunks": {"type": "integer", "description": "最大修改块数", "default": 3},
        },
        "required": ["file_path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "golf", "optimize", "simplify", "refactor"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path", "").strip()
        search_mode = kwargs.get("search_mode", "quick")
        max_hunks = kwargs.get("max_hunks", 3)

        if not file_path:
            return json.dumps({"error": "file_path is required"}, ensure_ascii=False)

        agent_prompt = _load_agent_prompt("proof-golfer")

        return json.dumps({
            "file_path": file_path,
            "search_mode": search_mode,
            "max_hunks": max_hunks,
            "status": "ready",
            "agent_prompt_length": len(agent_prompt),
            "instruction": """Golf 优化策略（按优先级）:
1. 直接性: by exact→t, apply+exact→exact, ext+rfl→rfl
2. 推理负担: 用 mathlib 标准引理替换自定义
3. 性能: linter simp 清理, 缩小 simp only
4. 长度: 验证后内联1-2次使用的绑定
每步用 lean4_check 验证，失败即回滚。max_hunks=3。""",
        }, ensure_ascii=False)


class Lean4ReviewTool(Tool):
    name = "lean4_review"
    description = "只读审查 Lean 4 证明：检查正确性、风格、mathlib 使用、性能"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Lean 文件路径"},
            "focus": {"type": "string", "description": "审查焦点: correctness, style, mathlib, performance, all", "default": "all"},
        },
        "required": ["file_path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "review", "audit", "code review", "quality"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path", "").strip()
        focus = kwargs.get("focus", "all")

        if not file_path:
            return json.dumps({"error": "file_path is required"}, ensure_ascii=False)

        return json.dumps({
            "file_path": file_path,
            "focus": focus,
            "status": "review_ready",
            "instruction": """审查维度:
1. 正确性: 编译是否通过? 有无 sorries? 是否引入非标准公理?
2. 风格: 100字符行宽? mathlib 命名约定? 缩进一致?
3. mathlib 使用: 是否充分利用已有引理? 是否有重复造轮子?
4. 性能: 编译时间? simp 性能? 是否使用了 calc 等重量级引用?
使用 lean4_check 和 lean4_get_diagnostics 获取编译信息。""",
        }, ensure_ascii=False)


class Lean4RefactorTool(Tool):
    name = "lean4_refactor"
    description = "重构 Lean 4 证明：利用 mathlib 引理、提取辅助函数、简化证明策略"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Lean 文件路径"},
            "strategy": {"type": "string", "description": "策略: mathlib_leverage, extract_helpers, simplify", "default": "mathlib_leverage"},
        },
        "required": ["file_path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "refactor", "mathlib", "helper", "simplify"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path", "").strip()
        strategy = kwargs.get("strategy", "mathlib_leverage")

        if not file_path:
            return json.dumps({"error": "file_path is required"}, ensure_ascii=False)

        return json.dumps({
            "file_path": file_path,
            "strategy": strategy,
            "status": "ready",
            "instruction": f"""重构策略: {strategy}
1. mathlib_leverage: 搜索 mathlib 用标准引理替换自定义证明
2. extract_helpers: 提取重复出现的证明块为独立 lemma
3. simplify: 简化 tactic 块（calc→rw, simp→exact 等）
使用 lean4_check 验证每次修改。""",
        }, ensure_ascii=False)


class Lean4LearnTool(Tool):
    name = "lean4_learn"
    description = "学习 Lean 4：mathlib 探索、概念教学、示例演示"
    parameters = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "学习主题/概念"},
            "mode": {"type": "string", "description": "模式: repo, mathlib, concept, example", "default": "concept"},
        },
        "required": ["topic"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "learn", "tutorial", "mathlib", "concept", "teaching"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        topic = kwargs.get("topic", "").strip()
        mode = kwargs.get("mode", "concept")

        if not topic:
            return json.dumps({"error": "topic is required"}, ensure_ascii=False)

        skill_ctx = _inject_skill_context()

        return json.dumps({
            "topic": topic,
            "mode": mode,
            "status": "ready",
            "skill_context_length": len(skill_ctx),
            "instruction": f"Lean 4 学习模式: {mode}。主题: {topic}。请提供 Lean 4 代码示例、tactic 解释、mathlib 引用等。",
        }, ensure_ascii=False)


class Lean4AgentTool(Tool):
    name = "lean4_agent"
    description = "运行 Lean 4 专用 agent（proof-golfer/axiom-eliminator/proof-repair/sorry-filler）"
    parameters = {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Agent 名称: proof-golfer, axiom-eliminator, proof-repair, sorry-filler-deep"},
            "file_path": {"type": "string", "description": "目标 Lean 文件路径"},
            "search_mode": {"type": "string", "description": "搜索模式（golfer 专用）", "default": "quick"},
        },
        "required": ["agent", "file_path"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "agent", "golfer", "axiom", "repair", "sorry"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        agent_name = kwargs.get("agent", "").strip()
        file_path = kwargs.get("file_path", "").strip()
        search_mode = kwargs.get("search_mode", "quick")

        if not agent_name or not file_path:
            return json.dumps({"error": "agent and file_path are required"}, ensure_ascii=False)

        agent_prompt = _load_agent_prompt(agent_name)
        if not agent_prompt:
            return json.dumps({"error": f"agent '{agent_name}' not found. Available: proof-golfer, axiom-eliminator, proof-repair, sorry-filler-deep"}, ensure_ascii=False)

        return json.dumps({
            "agent": agent_name,
            "file_path": file_path,
            "search_mode": search_mode,
            "status": "agent_loaded",
            "agent_prompt": agent_prompt[:5000],
        }, ensure_ascii=False)


def _find_mathlib_search() -> Optional[str]:
    return shutil.which("lean_local_search") or shutil.which("loogle")


class Lean4MathlibSearchTool(Tool):
    name = "lean4_mathlib_search"
    description = "搜索 mathlib 中的引理和定理"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询（自然语言或 Lean 表达式）"},
            "method": {"type": "string", "description": "搜索方法: leanfinder, loogle, local", "default": "local"},
            "max_results": {"type": "integer", "description": "最大结果数", "default": 10},
        },
        "required": ["query"],
    }
    category = "lean4"
    keywords = ["lean", "lean4", "mathlib", "search", "lemma", "loogle"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "").strip()
        method = kwargs.get("method", "local")
        max_results = kwargs.get("max_results", 10)

        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        search_bin = shutil.which(f"lean_{method}_search") or shutil.which(method)
        if search_bin is None and _find_lean4_mcp():
            result = _run_lean4_mcp(f"lean_{method}_search", "--query", query, "--max-results", str(max_results), timeout=30)
            return json.dumps(result, ensure_ascii=False)
        elif search_bin is None:
            return json.dumps({
                "query": query,
                "method": method,
                "status": "manual_search_needed",
                "instruction": f"lean4-mcp-proxy 不可用。请使用 https://loogle.lean-lang.org/ 搜索 '{query}'",
            }, ensure_ascii=False)

        try:
            result = subprocess.run(
                [search_bin, query, "--max-results", str(max_results)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
            )
            return json.dumps({
                "query": query,
                "method": method,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0,
            }, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"search timed out after 30s"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


def get_lean4_tools() -> List[Tool]:
    if not _check_lean4_available():
        logger.info("Lean 4 not found, skipping lean4 tools")
        return []

    tools = [
        Lean4CheckTool(),
        Lean4ProveTool(),
        Lean4FormalizeTool(),
        Lean4ReviewTool(),
        Lean4LearnTool(),
        Lean4MathlibSearchTool(),
    ]

    if _find_lean4_mcp():
        tools.extend([
            Lean4OpenFileTool(),
            Lean4GetDiagnosticsTool(),
            Lean4GetGoalStateTool(),
            Lean4GolfTool(),
        ])

    if _find_lake():
        tools.append(Lean4LakeBuildTool())

    if AGENTS_DIR.exists() and any(AGENTS_DIR.iterdir()):
        tools.extend([
            Lean4RefactorTool(),
            Lean4AgentTool(),
        ])

    return tools