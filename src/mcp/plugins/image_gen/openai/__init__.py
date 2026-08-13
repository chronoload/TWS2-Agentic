import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

API_MODEL = "gpt-image-2"

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2-low": {"display": "GPT Image 2 (Low)", "quality": "low", "speed": "~15s"},
    "gpt-image-2-medium": {"display": "GPT Image 2 (Medium)", "quality": "medium", "speed": "~40s"},
    "gpt-image-2-high": {"display": "GPT Image 2 (High)", "quality": "high", "speed": "~2min"},
}

DEFAULT_MODEL = "gpt-image-2-medium"

_SIZES = {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"}

IMAGE_GEN_SCHEMA = {
    "name": "image_gen",
    "description": "使用 OpenAI gpt-image-2 生成图像。",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "图像生成提示词"},
            "aspect_ratio": {
                "type": "string",
                "enum": ["landscape", "square", "portrait"],
                "description": "图像宽高比，默认 square",
            },
            "quality": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "生成质量，默认 medium",
            },
        },
        "required": ["prompt"],
    },
}


def _get_cache_dir() -> Path:
    cache_dir = Path.home() / ".ts2" / "cache" / "images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _save_b64_image(b64_data: str, prefix: str = "openai") -> Path:
    cache_dir = _get_cache_dir()
    timestamp = int(time.time())
    filename = f"{prefix}_{timestamp}.png"
    filepath = cache_dir / filename
    img_bytes = base64.b64decode(b64_data)
    filepath.write_bytes(img_bytes)
    return filepath


def _handle_image_gen(args: dict, **kw) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"success": False, "error": "prompt is required"})

    if not os.environ.get("OPENAI_API_KEY"):
        return json.dumps({"success": False, "error": "OPENAI_API_KEY not set"})

    try:
        import openai
    except ImportError:
        return json.dumps({"success": False, "error": "openai package not installed"})

    quality = args.get("quality", "medium")
    aspect = args.get("aspect_ratio", "square")
    size = _SIZES.get(aspect, _SIZES["square"])

    tier_id = f"gpt-image-2-{quality}"
    if tier_id not in _MODELS:
        tier_id = DEFAULT_MODEL

    try:
        client = openai.OpenAI()
        response = client.images.generate(
            model=API_MODEL,
            prompt=prompt,
            size=size,
            n=1,
            quality=_MODELS[tier_id]["quality"],
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

    data = getattr(response, "data", None) or []
    if not data:
        return json.dumps({"success": False, "error": "No image data returned"})

    first = data[0]
    b64 = getattr(first, "b64_json", None)
    url = getattr(first, "url", None)

    if b64:
        try:
            saved_path = _save_b64_image(b64, prefix=f"openai_{tier_id}")
            return json.dumps({
                "success": True,
                "image": str(saved_path),
                "model": tier_id,
                "prompt": prompt,
                "aspect_ratio": aspect,
            })
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})
    elif url:
        return json.dumps({"success": True, "image": url, "model": tier_id})

    return json.dumps({"success": False, "error": "No image data in response"})


def _check_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def register(ctx) -> None:
    ctx.register_tool(
        name="image_gen",
        toolset="image_gen",
        schema=IMAGE_GEN_SCHEMA,
        handler=_handle_image_gen,
        check_fn=_check_available,
        emoji="🎨",
    )
    logger.info("image_gen/openai plugin registered")
