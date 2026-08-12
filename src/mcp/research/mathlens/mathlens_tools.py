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

SKILLS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SKILLS_DIR / "scripts"
TEMPLATES_DIR = SKILLS_DIR / "templates"


def _find_manim() -> bool:
    return shutil.which("manim") is not None


def _find_edge_tts() -> bool:
    return shutil.which("edge-tts") is not None or shutil.which("uv") is not None


def _run_script(script_name: str, *args: str, timeout: int = 300, cwd: Optional[str] = None) -> Dict[str, Any]:
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}
    cmd = ["python", str(script_path)] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, cwd=cwd)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Script timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


class MathLensInitTool(Tool):
    name = "mathlens_init"
    description = "初始化 MathLens 数学教学视频项目（创建目录结构、拷贝模板）"
    parameters = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string", "description": "项目目录路径"},
        },
        "required": ["project_dir"],
    }
    category = "mathlens"
    keywords = ["mathlens", "init", "project", "setup"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        project_dir = kwargs.get("project_dir", "").strip()
        if not project_dir:
            return json.dumps({"error": "project_dir is required"}, ensure_ascii=False)
        init_script = SKILLS_DIR / "init.py"
        if init_script.exists():
            result = _run_script("init.py", project_dir, timeout=30)
            return json.dumps(result, ensure_ascii=False)
        project_path = Path(project_dir)
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "audio").mkdir(exist_ok=True)
        (project_path / "media").mkdir(exist_ok=True)
        templates_src = TEMPLATES_DIR
        if templates_src.exists():
            for f in templates_src.glob("*"):
                if f.is_file():
                    shutil.copy2(str(f), str(project_path / f.name))
        return json.dumps({"success": True, "project_dir": str(project_path)}, ensure_ascii=False)


class MathLensGenerateTTSTool(Tool):
    name = "mathlens_generate_tts"
    description = "使用 edge-tts 生成分镜脚本的 TTS 音频文件（含句级同步点）"
    parameters = {
        "type": "object",
        "properties": {
            "csv_path": {"type": "string", "description": "音频清单 CSV 路径"},
            "output_dir": {"type": "string", "description": "音频输出目录", "default": "./audio"},
            "voice": {"type": "string", "description": "TTS 音色（默认 xiaoxiao）", "default": "xiaoxiao"},
        },
        "required": ["csv_path"],
    }
    category = "mathlens"
    keywords = ["mathlens", "tts", "audio", "voice", "narration"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        csv_path = kwargs.get("csv_path", "").strip()
        if not csv_path:
            return json.dumps({"error": "csv_path is required"}, ensure_ascii=False)
        output_dir = kwargs.get("output_dir", "./audio")
        voice = kwargs.get("voice", "xiaoxiao")
        result = _run_script("generate_tts.py", csv_path, output_dir, "--voice", voice, timeout=300)
        return json.dumps(result, ensure_ascii=False)


class MathLensValidateAudioTool(Tool):
    name = "mathlens_validate_audio"
    description = "验证 TTS 音频文件并回写分镜脚本时长"
    parameters = {
        "type": "object",
        "properties": {
            "storyboard_path": {"type": "string", "description": "分镜脚本路径"},
            "audio_dir": {"type": "string", "description": "音频目录", "default": "./audio"},
        },
        "required": ["storyboard_path"],
    }
    category = "mathlens"
    keywords = ["mathlens", "audio", "validate", "duration"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        storyboard_path = kwargs.get("storyboard_path", "").strip()
        if not storyboard_path:
            return json.dumps({"error": "storyboard_path is required"}, ensure_ascii=False)
        audio_dir = kwargs.get("audio_dir", "./audio")
        result = _run_script("validate_audio.py", storyboard_path, audio_dir, timeout=30)
        return json.dumps(result, ensure_ascii=False)


class MathLensCheckTool(Tool):
    name = "mathlens_check"
    description = "检查 Manim 代码结构（calculate_geometry/assert_geometry/define_elements 等）"
    parameters = {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Manim 脚本路径（默认 script.py）", "default": "script.py"},
        },
        "required": [],
    }
    category = "mathlens"
    keywords = ["mathlens", "check", "manim", "structure"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        script_path = kwargs.get("script_path", "script.py")
        result = _run_script("check.py", script_path, timeout=15)
        return json.dumps(result, ensure_ascii=False)


class MathLensRenderTool(Tool):
    name = "mathlens_render"
    description = "渲染 MathLens Manim 教学视频（检查+渲染+拷贝到根目录）"
    parameters = {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Manim 脚本路径", "default": "script.py"},
            "scene_name": {"type": "string", "description": "场景类名", "default": "MathScene"},
            "quality": {"type": "string", "description": "渲染质量: l/m/h/k", "default": "h"},
            "no_check": {"type": "boolean", "description": "跳过检查", "default": False},
        },
        "required": [],
    }
    category = "mathlens"
    keywords = ["mathlens", "render", "video", "manim"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        script_path = kwargs.get("script_path", "script.py")
        scene_name = kwargs.get("scene_name", "MathScene")
        quality = kwargs.get("quality", "h")
        no_check = kwargs.get("no_check", False)
        args = ["-f", script_path, "-s", scene_name, "-q", quality]
        if no_check:
            args.append("--no-check")
        result = _run_script("render.py", *args, timeout=600)
        return json.dumps(result, ensure_ascii=False)


def get_mathlens_tools() -> List[Tool]:
    if not _find_manim():
        logger.info("Manim not found, skipping MathLens tools")
        return []
    return [
        MathLensInitTool(),
        MathLensGenerateTTSTool(),
        MathLensValidateAudioTool(),
        MathLensCheckTool(),
        MathLensRenderTool(),
    ]
