"""多模态媒体工具 — 文件类型检测、base64 编码、图片尺寸嗅探。

借鉴 kimi-cli (read_media.py + utils.py) 的设计：
- magic bytes 嗅探优先，后缀名兜底
- 图片 → data:image/xxx;base64,... data URL
- 视频 → data:video/xxx;base64,... data URL
- 图片尺寸从文件头提取（不依赖 PIL）
"""

import base64
import mimetypes
import struct
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal, Optional, Tuple

# ── 常量 ──────────────────────────────────────────────────────

MEDIA_SNIFF_BYTES = 512
MAX_MEDIA_MEGABYTES = 100
MAX_MEDIA_BYTES = MAX_MEDIA_MEGABYTES << 20

# ── MIME 映射表 ──────────────────────────────────────────────

_EXTRA_MIME_TYPES = {
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".mkv": "video/x-matroska",
    ".m4v": "video/x-m4v",
    ".3gp": "video/3gpp",
    ".3g2": "video/3gpp2",
}

for _suffix, _mime in _EXTRA_MIME_TYPES.items():
    mimetypes.add_type(_mime, _suffix)

_IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".svgz": "image/svg+xml",
}

_VIDEO_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".wmv": "video/x-ms-wmv",
    ".webm": "video/webm",
    ".m4v": "video/x-m4v",
    ".flv": "video/x-flv",
    ".3gp": "video/3gpp",
    ".3g2": "video/3gpp2",
}

_ASF_HEADER = b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c"

_FTYP_IMAGE_BRANDS = {
    "avif": "image/avif",
    "avis": "image/avif",
    "heic": "image/heic",
    "heif": "image/heif",
    "heix": "image/heif",
    "hevc": "image/heic",
    "mif1": "image/heif",
    "msf1": "image/heif",
}

_FTYP_VIDEO_BRANDS = {
    "isom": "video/mp4",
    "iso2": "video/mp4",
    "iso5": "video/mp4",
    "mp41": "video/mp4",
    "mp42": "video/mp4",
    "avc1": "video/mp4",
    "mp4v": "video/mp4",
    "m4v": "video/x-m4v",
    "qt": "video/quicktime",
    "3gp4": "video/3gpp",
    "3gp5": "video/3gpp",
    "3gp6": "video/3gpp",
    "3gp7": "video/3gpp",
    "3g2": "video/3gpp2",
}

# ── 数据类型 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class FileType:
    kind: Literal["text", "image", "video", "unknown"]
    mime_type: str


# ── magic bytes 嗅探 ─────────────────────────────────────────


def _sniff_ftyp_brand(header: bytes) -> Optional[str]:
    if len(header) < 12 or header[4:8] != b"ftyp":
        return None
    brand = header[8:12].decode("ascii", errors="ignore").lower()
    return brand.strip() or None


def sniff_media_from_magic(data: bytes) -> Optional[FileType]:
    """从文件头 magic bytes 判断媒体类型。"""
    header = data[:MEDIA_SNIFF_BYTES]

    # PNG
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileType(kind="image", mime_type="image/png")
    # JPEG
    if header.startswith(b"\xff\xd8\xff"):
        return FileType(kind="image", mime_type="image/jpeg")
    # GIF
    if header.startswith((b"GIF87a", b"GIF89a")):
        return FileType(kind="image", mime_type="image/gif")
    # BMP
    if header.startswith(b"BM"):
        return FileType(kind="image", mime_type="image/bmp")
    # TIFF
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return FileType(kind="image", mime_type="image/tiff")
    # ICO
    if header.startswith(b"\x00\x00\x01\x00"):
        return FileType(kind="image", mime_type="image/x-icon")
    # RIFF → WEBP / AVI
    if header.startswith(b"RIFF") and len(header) >= 12:
        chunk = header[8:12]
        if chunk == b"WEBP":
            return FileType(kind="image", mime_type="image/webp")
        if chunk == b"AVI ":
            return FileType(kind="video", mime_type="video/x-msvideo")
    # FLV
    if header.startswith(b"FLV"):
        return FileType(kind="video", mime_type="video/x-flv")
    # ASF/WMV
    if header.startswith(_ASF_HEADER):
        return FileType(kind="video", mime_type="video/x-ms-wmv")
    # Matroska / WebM
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        lowered = header.lower()
        if b"webm" in lowered:
            return FileType(kind="video", mime_type="video/webm")
        if b"matroska" in lowered:
            return FileType(kind="video", mime_type="video/x-matroska")
    # MP4/MOV (ftyp box)
    if brand := _sniff_ftyp_brand(header):
        if brand in _FTYP_IMAGE_BRANDS:
            return FileType(kind="image", mime_type=_FTYP_IMAGE_BRANDS[brand])
        if brand in _FTYP_VIDEO_BRANDS:
            return FileType(kind="video", mime_type=_FTYP_VIDEO_BRANDS[brand])

    return None


def detect_file_type(path: str, header: Optional[bytes] = None) -> FileType:
    """检测文件类型：后缀名 + magic bytes 综合判断。"""
    suffix = PurePath(path).suffix.lower()

    # 1. 后缀名快速查表
    media_hint: Optional[FileType] = None
    if suffix in _IMAGE_MIME_BY_SUFFIX:
        media_hint = FileType(kind="image", mime_type=_IMAGE_MIME_BY_SUFFIX[suffix])
    elif suffix in _VIDEO_MIME_BY_SUFFIX:
        media_hint = FileType(kind="video", mime_type=_VIDEO_MIME_BY_SUFFIX[suffix])
    else:
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type:
            if mime_type.startswith("image/"):
                media_hint = FileType(kind="image", mime_type=mime_type)
            elif mime_type.startswith("video/"):
                media_hint = FileType(kind="video", mime_type=mime_type)

    if media_hint and media_hint.kind in ("image", "video"):
        return media_hint

    # 2. magic bytes 嗅探
    if header is not None:
        sniffed = sniff_media_from_magic(header)
        if sniffed:
            if media_hint and sniffed.kind != media_hint.kind:
                return FileType(kind="unknown", mime_type="")
            return sniffed
        # NUL 字节 → 二进制
        if b"\x00" in header:
            return FileType(kind="unknown", mime_type="")

    if media_hint:
        return media_hint

    return FileType(kind="text", mime_type="text/plain")


# ── 图片尺寸嗅探（不依赖 PIL）──────────────────────────────


def sniff_image_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """从文件头提取图片原始尺寸 (width, height)，不依赖 PIL。

    支持 PNG / JPEG / GIF / BMP / WebP。
    """
    try:
        # PNG: IHDR chunk at offset 16
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            w = struct.unpack(">I", data[16:20])[0]
            h = struct.unpack(">I", data[20:24])[0]
            return (w, h)

        # JPEG: SOF0/SOF2 marker
        if data.startswith(b"\xff\xd8\xff"):
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC2):  # SOF0, SOF2
                    h = struct.unpack(">H", data[i + 5:i + 7])[0]
                    w = struct.unpack(">H", data[i + 7:i + 9])[0]
                    return (w, h)
                if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9):
                    i += 2
                else:
                    seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
                    i += 2 + seg_len

        # GIF
        if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
            w = struct.unpack("<H", data[6:8])[0]
            h = struct.unpack("<H", data[8:10])[0]
            return (w, h)

        # BMP
        if data.startswith(b"BM") and len(data) >= 26:
            w = struct.unpack("<I", data[18:22])[0]
            h = abs(struct.unpack("<i", data[22:26])[0])
            return (w, h)

        # WebP
        if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
            # VP8 lossy
            if data[12:16] == b"VP8 " and len(data) >= 30:
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return (w, h)
            # VP8L lossless
            if data[12:16] == b"VP8L" and len(data) >= 25:
                bits = struct.unpack("<I", data[21:25])[0]
                w = (bits & 0x3FFF) + 1
                h = ((bits >> 14) & 0x3FFF) + 1
                return (w, h)
    except Exception:
        pass

    return None


# ── base64 data URL 编码 ─────────────────────────────────────


def to_data_url(mime_type: str, data: bytes) -> str:
    """将二进制数据编码为 data URL。"""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def encode_media_file(file_path: str) -> dict:
    """读取媒体文件并返回编码结果。

    Returns:
        {
            "kind": "image" | "video",
            "mime_type": str,
            "data_url": str,          # data:image/xxx;base64,...
            "size": int,              # 文件字节数
            "dimensions": [w, h] | None,  # 图片尺寸
        }
    Raises:
        ValueError: 文件不存在 / 非媒体 / 过大
    """
    from pathlib import Path

    p = Path(file_path)
    if not p.exists():
        raise ValueError(f"文件不存在: {file_path}")
    if not p.is_file():
        raise ValueError(f"不是文件: {file_path}")

    size = p.stat().st_size
    if size == 0:
        raise ValueError(f"文件为空: {file_path}")
    if size > MAX_MEDIA_BYTES:
        raise ValueError(f"文件过大 ({size} bytes)，上限 {MAX_MEDIA_MEGABYTES}MB")

    header = p.read_bytes()[:MEDIA_SNIFF_BYTES]
    file_type = detect_file_type(file_path, header)

    if file_type.kind not in ("image", "video"):
        raise ValueError(f"不支持的文件类型: {file_type.kind} ({file_type.mime_type})")

    data = p.read_bytes()
    data_url = to_data_url(file_type.mime_type, data)
    dimensions = sniff_image_dimensions(data) if file_type.kind == "image" else None

    return {
        "kind": file_type.kind,
        "mime_type": file_type.mime_type,
        "data_url": data_url,
        "size": size,
        "dimensions": list(dimensions) if dimensions else None,
    }


def build_multimodal_content(text: str, attachments: list) -> list:
    """构建 OpenAI 多模态消息 content（list of parts）。

    Args:
        text: 文本内容
        attachments: [{"kind": "image"|"video", "data_url": "...", "path": "..."}]

    Returns:
        [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}, ...]
    """
    parts = []

    if text:
        parts.append({"type": "text", "text": text})

    for att in attachments:
        kind = att.get("kind", "image")
        data_url = att.get("data_url", "")
        path = att.get("path", "")

        if kind == "image":
            parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        elif kind == "video":
            # OpenAI 兼容格式：部分提供商支持 video_url
            parts.append({
                "type": "video_url",
                "video_url": {"url": data_url},
            })

        # 路径标签
        if path:
            parts.append({"type": "text", "text": f"<{kind} path=\"{path}\"/>"})

    return parts
