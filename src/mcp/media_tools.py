"""ReadMediaFile 工具 — 读取图片/视频文件作为多模态内容。

借鉴 kimi-cli ReadMediaFile 的设计：
- 返回 data URL 格式的 base64 编码
- 包含文件类型、尺寸等元信息
- 支持 image_url / video_url content parts
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .media_utils import (
    MAX_MEDIA_MEGABYTES,
    detect_file_type,
    encode_media_file,
    sniff_image_dimensions,
    to_data_url,
)
from .tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class ReadMediaFileTool(Tool):
    name = "read_media_file"
    category = "file_io"
    keywords = ["image", "video", "media", "图片", "视频", "截图", "照片", "多媒体", "base64"]
    model_hint = (
        "[何时使用] 查看图片或视频文件内容。支持 PNG/JPEG/GIF/WebP/BMP/MP4/WebM/MKV 等格式。\n"
        "[参数说明]\n"
        "- path: 必填，图片或视频文件路径\n"
        "[注意] 文本文件请用 read_file，本工具仅处理图片和视频"
    )
    description = f"读取图片或视频文件，返回 base64 编码的多模态内容。支持常见图片和视频格式，最大 {MAX_MEDIA_MEGABYTES}MB。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "【必填】图片或视频文件路径（相对于工作目录或绝对路径）",
            },
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str = "") -> str:
        if not path:
            return ToolResult.err("文件路径不能为空").to_json()

        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}").to_json()

            result = encode_media_file(str(full_path))

            # 构建人类可读摘要
            size_hint = ""
            if result["dimensions"]:
                w, h = result["dimensions"]
                size_hint = f"，原始尺寸 {w}x{h}px"

            summary = (
                f"已加载 {result['kind']} 文件 `{path}` "
                f"({result['mime_type']}, {result['size']} bytes{size_hint})。"
            )

            # 返回 JSON，包含 data_url 和元信息
            # 前端/中间件可以从 data_url 提取 content parts
            return ToolResult.ok(json.dumps({
                "kind": result["kind"],
                "mime_type": result["mime_type"],
                "data_url": result["data_url"],
                "size": result["size"],
                "dimensions": result["dimensions"],
                "summary": summary,
            }, ensure_ascii=False)).to_json()

        except ValueError as e:
            return ToolResult.err(str(e)).to_json()
        except Exception as e:
            logger.warning(f"ReadMediaFile 失败: {path}: {e}")
            return ToolResult.err(f"读取媒体文件失败: {path}。错误: {e}").to_json()


def get_media_tools(base_dir=None):
    """返回媒体相关工具列表。"""
    return [ReadMediaFileTool(base_dir=base_dir)]
