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
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _find_manim_mcp() -> Optional[str]:
    path = shutil.which("manim-mcp")
    if path:
        return path
    try:
        result = subprocess.run(["pip", "show", "manim-mcp"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        if result.returncode == 0:
            return "manim-mcp"
    except Exception:
        pass
    return None


def _find_manim() -> Optional[str]:
    return shutil.which("manim")


def _run_manim_mcp(*args: str, timeout: int = 300, stdin_data: Optional[str] = None) -> Dict[str, Any]:
    mcp = _find_manim_mcp()
    if mcp is None:
        return {"error": "manim-mcp not found. Install: pip install -e '.[rag]'"}
    cmd = [mcp] + list(args)
    env = os.environ.copy()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=env, input=stdin_data)
        if result.returncode != 0:
            return {"error": result.stderr.strip() or result.stdout.strip(), "returncode": result.returncode}
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"error": f"manim-mcp timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _run_manim(script_path: str, scene_name: str, quality: str = "h", timeout: int = 300) -> Dict[str, Any]:
    manim = _find_manim()
    if manim is None:
        return {"error": "manim not found on PATH. Install: pip install manimgl"}
    cmd = [manim, f"-pq{quality}", script_path, scene_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"manim render timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _check_manim_available() -> bool:
    return _find_manim_mcp() is not None or _find_manim() is not None


def _load_prompt(prompt_name: str) -> str:
    if not PROMPTS_DIR.exists():
        return ""
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


def _load_skill_context() -> str:
    result = ""
    for skill_name in ["manimce-best-practices", "manimgl-best-practices"]:
        skill_path = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_path.exists():
            result += skill_path.read_text(encoding="utf-8") + "\n"
    return result


class ManimGenerateTool(Tool):
    name = "manim_generate"
    description = "使用 manim-mcp 从文本描述生成动画视频"
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "动画描述（英文）"},
            "mode": {"type": "string", "description": "生成模式: simple 或 advanced", "default": "simple"},
            "quality": {"type": "string", "description": "渲染质量: l(480p)/m(720p)/h(1080p)/k(4K)", "default": "h"},
            "audio": {"type": "boolean", "description": "是否生成配音", "default": False},
        },
        "required": ["prompt"],
    }
    category = "manim"
    keywords = ["manim", "animation", "video", "generate", "3b1b"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return json.dumps({"error": "prompt is required"}, ensure_ascii=False)
        if _find_manim_mcp() is None:
            skill_ctx = _load_skill_context()
            return json.dumps({
                "error": "manim-mcp not available",
                "alternative": "use manim_render with a pre-written script",
                "skill_context_length": len(skill_ctx),
            }, ensure_ascii=False)
        mode = kwargs.get("mode", "simple")
        quality = kwargs.get("quality", "h")
        audio = kwargs.get("audio", False)
        args = ["gen", prompt, "--mode", mode, "--quality", quality]
        if audio:
            args.append("--audio")
        result = _run_manim_mcp(*args, timeout=600)
        return json.dumps(result, ensure_ascii=False)


class ManimEditTool(Tool):
    name = "manim_edit"
    description = "编辑已有的 manim-mcp 渲染结果"
    parameters = {
        "type": "object",
        "properties": {
            "render_id": {"type": "string", "description": "渲染 ID"},
            "instruction": {"type": "string", "description": "编辑指令"},
        },
        "required": ["render_id", "instruction"],
    }
    category = "manim"
    keywords = ["manim", "animation", "edit", "modify"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        render_id = kwargs.get("render_id", "").strip()
        instruction = kwargs.get("instruction", "").strip()
        if not render_id or not instruction:
            return json.dumps({"error": "render_id and instruction are required"}, ensure_ascii=False)
        if _find_manim_mcp() is None:
            return json.dumps({"error": "manim-mcp not available"}, ensure_ascii=False)
        result = _run_manim_mcp("edit", render_id, instruction, timeout=600)
        return json.dumps(result, ensure_ascii=False)


class ManimListRendersTool(Tool):
    name = "manim_list_renders"
    description = "列出 manim-mcp 的渲染历史"
    parameters = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "过滤状态: completed/failed/running", "default": ""},
            "limit": {"type": "integer", "description": "返回数量", "default": 10},
        },
        "required": [],
    }
    category = "manim"
    keywords = ["manim", "render", "list", "history"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        if _find_manim_mcp() is None:
            return json.dumps({"error": "manim-mcp not available"}, ensure_ascii=False)
        args = ["list", "--limit", str(kwargs.get("limit", 10))]
        status = kwargs.get("status", "").strip()
        if status:
            args.extend(["--status", status])
        result = _run_manim_mcp(*args, timeout=30)
        return json.dumps(result, ensure_ascii=False)


class ManimRenderTool(Tool):
    name = "manim_render"
    description = "直接使用 manim 渲染 Python 脚本中的场景"
    parameters = {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Python 脚本路径"},
            "scene_name": {"type": "string", "description": "场景类名"},
            "quality": {"type": "string", "description": "渲染质量: l/m/h/k", "default": "h"},
            "timeout": {"type": "integer", "description": "超时秒数", "default": 300},
        },
        "required": ["script_path", "scene_name"],
    }
    category = "manim"
    keywords = ["manim", "render", "video", "scene"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        script_path = kwargs.get("script_path", "").strip()
        scene_name = kwargs.get("scene_name", "").strip()
        if not script_path or not scene_name:
            return json.dumps({"error": "script_path and scene_name are required"}, ensure_ascii=False)
        quality = kwargs.get("quality", "h")
        timeout = kwargs.get("timeout", 300)
        result = _run_manim(script_path, scene_name, quality, timeout)
        return json.dumps(result, ensure_ascii=False)


class ManimRagSearchTool(Tool):
    name = "manim_rag_search"
    description = "搜索 manim-mcp RAG 数据库中的相似场景"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "collection": {"type": "string", "description": "集合名: manim_scenes/manim_api/animation_patterns/manim_docs/error_patterns", "default": "manim_scenes"},
            "limit": {"type": "integer", "description": "返回数量", "default": 5},
        },
        "required": ["query"],
    }
    category = "manim"
    keywords = ["manim", "rag", "search", "scene", "api"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)
        if _find_manim_mcp() is None:
            return json.dumps({"error": "manim-mcp not available"}, ensure_ascii=False)
        collection = kwargs.get("collection", "manim_scenes")
        limit = kwargs.get("limit", 5)
        result = _run_manim_mcp("rag-search", "--query", query, "--collection", collection, "--limit", str(limit), timeout=30)
        return json.dumps(result, ensure_ascii=False)


class ManimConceptAnalyzeTool(Tool):
    name = "manim_concept_analyze"
    description = "分析数学/科学概念，推荐最佳动画方案和可视化策略"
    parameters = {
        "type": "object",
        "properties": {
            "concept": {"type": "string", "description": "要可视化的概念描述"},
            "style": {"type": "string", "description": "动画风格: 3b1b, textbook, presentation, short", "default": "3b1b"},
            "target_audience": {"type": "string", "description": "目标受众: general, undergraduate, graduate, expert", "default": "general"},
        },
        "required": ["concept"],
    }
    category = "manim"
    keywords = ["manim", "concept", "analyze", "visualize", "strategy", "plan"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        concept = kwargs.get("concept", "").strip()
        style = kwargs.get("style", "3b1b")
        target_audience = kwargs.get("target_audience", "general")

        if not concept:
            return json.dumps({"error": "concept is required"}, ensure_ascii=False)

        concept_analyzer_prompt = _load_prompt("concept_analyzer")
        skill_ctx = _load_skill_context()

        return json.dumps({
            "concept": concept,
            "style": style,
            "target_audience": target_audience,
            "status": "analyzed",
            "concept_analyzer_length": len(concept_analyzer_prompt),
            "skill_context_length": len(skill_ctx),
            "instruction": f"""分析概念 "{concept}" 的可视化策略:
1. 核心要素: 识别需要展示的关键数学概念
2. 动画方案: 推荐 scene 结构（intro/build/insight/outro）
3. 视觉元素: 推荐 mobjects（axes, graphs, text, shapes）
4. 动画序列: 推荐 transform/create/uncreate 动画序列
5. 风格参考: {style} 风格，目标受众 {target_audience}""",
        }, ensure_ascii=False)


class ManimCodeReviewTool(Tool):
    name = "manim_code_review"
    description = "审查 Manim 代码：检查正确性、风格、性能、渲染风险"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Manim 代码"},
            "script_path": {"type": "string", "description": "或指定脚本路径"},
            "engine": {"type": "string", "description": "渲染引擎: manimce, manimgl", "default": "manimce"},
        },
        "required": ["code"],
    }
    category = "manim"
    keywords = ["manim", "review", "code", "audit", "quality"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        code = kwargs.get("code", "").strip()
        script_path = kwargs.get("script_path", "").strip()
        engine = kwargs.get("engine", "manimce")

        if script_path:
            try:
                code = Path(script_path).read_text(encoding="utf-8")
            except Exception:
                pass

        if not code.strip():
            return json.dumps({"error": "code is required"}, ensure_ascii=False)

        reviewer_prompt = _load_prompt("code_reviewer")
        line_count = len(code.splitlines())

        return json.dumps({
            "status": "review_ready",
            "engine": engine,
            "line_count": line_count,
            "reviewer_prompt_length": len(reviewer_prompt),
            "instruction": f"""审查 Manim {engine} 代码 ({line_count}行):
1. 语法正确性: import 是否正确? 类名/方法名是否正确?
2. 风格: 是否遵循 {engine} 最佳实践? 是否使用 CONFIG?
3. 性能: 是否有不必要的重绘? 对象数量是否合理?
4. 渲染风险: 是否有可能导致 OOM? 超长时间?
5. 可移植性: 是否依赖外部资源? 文件路径是否硬编码?

请列出具体问题、严重程度和修复建议。""",
        }, ensure_ascii=False)


class ManimSelfCritiqueTool(Tool):
    name = "manim_self_critique"
    description = "Manim 动画自我审查：验证输出、检查布局、确认质量"
    parameters = {
        "type": "object",
        "properties": {
            "render_id": {"type": "string", "description": "渲染 ID"},
            "check_aspects": {"type": "array", "items": {"type": "string"}, "description": "检查方面: layout, timing, color, text, math, audio"},
        },
        "required": ["render_id"],
    }
    category = "manim"
    keywords = ["manim", "critique", "verify", "quality", "self"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        render_id = kwargs.get("render_id", "").strip()
        check_aspects = kwargs.get("check_aspects", ["layout", "timing", "color", "text", "math"])

        if not render_id:
            return json.dumps({"error": "render_id is required"}, ensure_ascii=False)

        critique_system = _load_prompt("self_critique_system")
        critique_verify = _load_prompt("self_critique_verify")
        critique_fix = _load_prompt("self_critique_fix")

        return json.dumps({
            "render_id": render_id,
            "check_aspects": check_aspects,
            "status": "critique_ready",
            "prompts_loaded": {
                "system": len(critique_system),
                "verify": len(critique_verify),
                "fix": len(critique_fix),
            },
            "instruction": f"""自我审查渲染 {render_id}:
检查方面: {', '.join(check_aspects)}
1. layout: 元素是否重叠? 是否有元素超出画面?
2. timing: 动画节奏是否合理? 是否有卡顿?
3. color: 色彩是否协调? 对比度是否足够?
4. text: 文字是否清晰可读? 大小是否合适?
5. math: 数学公式是否正确渲染? 对齐是否准确?
6. audio: 配音是否同步?（如有）

对每个问题评分: passed / minor / major / critical。""",
        }, ensure_ascii=False)


class ManimTTSGenerateTool(Tool):
    name = "manim_tts_generate"
    description = "为 Manim 动画生成 TTS 配音旁白"
    parameters = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "旁白文本（按场景分段）"},
            "script_path": {"type": "string", "description": "或指定旁白脚本路径"},
            "voice": {"type": "string", "description": "TTS 语音: Puck, Charon, Kore, Fenrir, Aoede", "default": "Puck"},
            "output_dir": {"type": "string", "description": "音频输出目录", "default": "./audio"},
        },
        "required": ["script"],
    }
    category = "manim"
    keywords = ["manim", "tts", "audio", "narration", "voice", "speech"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        script = kwargs.get("script", "").strip()
        script_path = kwargs.get("script_path", "").strip()
        voice = kwargs.get("voice", "Puck")
        output_dir = kwargs.get("output_dir", "./audio")

        if script_path:
            try:
                script = Path(script_path).read_text(encoding="utf-8")
            except Exception:
                pass

        if not script.strip():
            return json.dumps({"error": "script is required"}, ensure_ascii=False)

        narration_prompt = _load_prompt("tts_narration_script")
        fallback_prompt = _load_prompt("tts_narration_fallback")

        return json.dumps({
            "status": "tts_ready",
            "voice": voice,
            "output_dir": output_dir,
            "script_length": len(script),
            "narration_prompt_loaded": len(narration_prompt) > 0,
            "fallback_prompt_loaded": len(fallback_prompt) > 0,
            "instruction": f"""生成 TTS 配音:
1. 解析旁白脚本，按场景分段
2. 使用语音: {voice}，输出到: {output_dir}
3. 生成 audio_segments.json 记录每个音频片段的起止时间
4. 推荐 Puck（男声，中性）或 Fenrir（男声，深沉）""",
        }, ensure_ascii=False)


class ManimSchemaGenerateTool(Tool):
    name = "manim_schema_generate"
    description = "生成动画 Schema：从概念描述生成结构化的分镜脚本"
    parameters = {
        "type": "object",
        "properties": {
            "concept": {"type": "string", "description": "概念描述"},
            "use_latex": {"type": "boolean", "description": "是否使用 LaTeX 数学公式", "default": True},
            "scene_count": {"type": "integer", "description": "建议场景数", "default": 5},
        },
        "required": ["concept"],
    }
    category = "manim"
    keywords = ["manim", "schema", "storyboard", "script", "plan", "scene"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        concept = kwargs.get("concept", "").strip()
        use_latex = kwargs.get("use_latex", True)
        scene_count = kwargs.get("scene_count", 5)

        if not concept:
            return json.dumps({"error": "concept is required"}, ensure_ascii=False)

        schema_system = _load_prompt("schema_generator_system")
        schema_narration = _load_prompt("schema_generator_narration")
        scene_planner = _load_prompt("scene_planner")

        latex_instructions = _load_prompt("latex_instructions" if use_latex else "no_latex_instructions")

        return json.dumps({
            "concept": concept,
            "use_latex": use_latex,
            "scene_count": scene_count,
            "status": "schema_ready",
            "prompts_loaded": {
                "schema_system": len(schema_system),
                "schema_narration": len(schema_narration),
                "scene_planner": len(scene_planner),
                "latex_instructions": len(latex_instructions),
            },
            "instruction": f"""生成动画 Schema:
1. 为 "{concept}" 设计 {scene_count} 个场景
2. 每个场景包含: scene_id, title, description, visual_elements, manim_code_skeleton, narration, duration
3. LaTeX: {'启用' if use_latex else '禁用'}
4. 输出格式: JSON array of scene objects
5. 参考 scene_planner 和 schema_generator 提示词""",
        }, ensure_ascii=False)


class ManimSkillsListTool(Tool):
    name = "manim_skills_list"
    description = "列出可用的 Manim 技能：manimce-best-practices 和 manimgl-best-practices"
    parameters = {
        "type": "object",
        "properties": {
            "engine": {"type": "string", "description": "引擎: manimce, manimgl, all", "default": "all"},
        },
        "required": [],
    }
    category = "manim"
    keywords = ["manim", "skills", "list", "best-practices"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        engine = kwargs.get("engine", "all")
        skills_info = {}

        for skill_name in ["manimce-best-practices", "manimgl-best-practices"]:
            if engine != "all" and skill_name != f"{engine}-best-practices":
                continue
            skill_dir = SKILLS_DIR / skill_name
            if not skill_dir.exists():
                continue
            info = {"name": skill_name, "rules": [], "examples": [], "templates": [], "references": []}
            rules_dir = skill_dir / "rules"
            if rules_dir.exists():
                info["rules"] = [p.stem for p in rules_dir.glob("*.md")]
            examples_dir = skill_dir / "examples"
            if examples_dir.exists():
                info["examples"] = [p.name for p in examples_dir.glob("*.py")]
            templates_dir = skill_dir / "templates"
            if templates_dir.exists():
                info["templates"] = [p.name for p in templates_dir.glob("*.py")]
            references_dir = skill_dir / "references"
            if references_dir.exists():
                info["references"] = [p.name for p in references_dir.glob("*.md")]
            skills_info[skill_name] = info

        return json.dumps({"skills": skills_info}, ensure_ascii=False)


def get_manim_tools() -> List[Tool]:
    if not _check_manim_available():
        logger.info("Manim not found, skipping manim tools")
        return []

    tools = [
        ManimRenderTool(),
        ManimConceptAnalyzeTool(),
        ManimCodeReviewTool(),
        ManimSkillsListTool(),
    ]

    if SKILLS_DIR.exists():
        tools.extend([
            ManimSchemaGenerateTool(),
            ManimSelfCritiqueTool(),
            ManimTTSGenerateTool(),
        ])

    if _find_manim_mcp():
        tools.extend([
            ManimGenerateTool(),
            ManimEditTool(),
            ManimListRendersTool(),
            ManimRagSearchTool(),
        ])

    if PROMPTS_DIR.exists() and any(PROMPTS_DIR.iterdir()):
        pass

    return tools