import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SkillCategory(Enum):
    PUBLIC = "public"
    CUSTOM = "custom"


@dataclass
class MCPServerRef:
    """MCP 远程服务引用"""
    name: str = ""
    transport: str = "http"  # http, sse, stdio
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    api_key_env: str = ""  # 环境变量名，如 BAIDU_API_KEY
    api_key_doc: str = ""  # API Key 获取文档链接


@dataclass
class SkillManifest:
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    platforms: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    category: str = ""
    allowed_tools: Optional[List[str]] = None
    enabled: bool = True
    pinned: bool = False
    # 新增字段
    api_key_ref: str = ""  # 环境变量名，如 BAIDU_API_KEY
    scripts: Dict[str, str] = field(default_factory=dict)  # {"main": "scripts/search.py"}
    references: List[str] = field(default_factory=list)  # ["references/apikey-fetch.md"]
    mcp_server: Optional[MCPServerRef] = None  # 关联的 MCP 远程服务


@dataclass
class Skill:
    name: str
    description: str
    skill_dir: Path = field(default_factory=Path)
    skill_file: Path = field(default_factory=Path)
    relative_path: Path = field(default_factory=Path)
    category: SkillCategory = SkillCategory.CUSTOM
    allowed_tools: Optional[List[str]] = None
    enabled: bool = False
    version: str = "1.0.0"
    author: str = ""
    platforms: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    pinned: bool = False
    manifest: Optional[SkillManifest] = None
    status: str = "active"
    content: str = ""
    # 新增字段
    api_key_ref: str = ""
    scripts: Dict[str, str] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)
    mcp_server: Optional[MCPServerRef] = None

    @classmethod
    def from_skill_md(cls, skill_dir: Path) -> Optional["Skill"]:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return None

        content = skill_file.read_text(encoding="utf-8")
        manifest = cls._parse_frontmatter(content)
        if manifest is None:
            return None

        return cls(
            name=manifest.name,
            description=manifest.description,
            skill_dir=skill_dir,
            skill_file=skill_file,
            relative_path=skill_dir.name,
            category=SkillCategory.CUSTOM if manifest.category == "custom" else SkillCategory.PUBLIC,
            allowed_tools=manifest.allowed_tools,
            enabled=manifest.enabled,
            version=manifest.version,
            author=manifest.author,
            platforms=manifest.platforms,
            tags=manifest.tags,
            pinned=manifest.pinned,
            manifest=manifest,
            content=content,
            api_key_ref=manifest.api_key_ref,
            scripts=manifest.scripts,
            references=manifest.references,
            mcp_server=manifest.mcp_server,
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> Optional[SkillManifest]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return None

        frontmatter_str = match.group(1)
        manifest = SkillManifest()

        try:
            import yaml
            data = yaml.safe_load(frontmatter_str)
            if not isinstance(data, dict):
                return manifest
        except ImportError:
            data = {}
            for line in frontmatter_str.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    data[key] = value
            if "name" not in data:
                return manifest
        except Exception:
            return manifest

        if isinstance(data, dict):
            manifest.name = data.get("name", "")
            manifest.description = data.get("description", "")
            manifest.version = data.get("version", "1.0.0")
            manifest.author = data.get("author", "")
            manifest.platforms = data.get("platforms", [])
            manifest.tags = data.get("tags", [])
            manifest.category = data.get("category", "")
            manifest.allowed_tools = data.get("allowed_tools")
            manifest.enabled = data.get("enabled", True)
            manifest.pinned = data.get("pinned", False)
            # 新增字段解析
            manifest.api_key_ref = data.get("api_key_ref", "")
            manifest.scripts = data.get("scripts", {})
            manifest.references = data.get("references", [])

            # 解析 mcp_server 引用
            mcp_data = data.get("mcp_server")
            if isinstance(mcp_data, dict):
                manifest.mcp_server = MCPServerRef(
                    name=mcp_data.get("name", ""),
                    transport=mcp_data.get("transport", "http"),
                    url=mcp_data.get("url", ""),
                    headers=mcp_data.get("headers", {}),
                    api_key_env=mcp_data.get("api_key_env", ""),
                    api_key_doc=mcp_data.get("api_key_doc", ""),
                )

            metadata = data.get("metadata", {})
            if isinstance(metadata, dict):
                for source_key in ("hermes", "ts2"):
                    source_meta = metadata.get(source_key, {})
                    if isinstance(source_meta, dict):
                        if not manifest.tags and "tags" in source_meta:
                            manifest.tags = source_meta["tags"]
                        if not manifest.category and "category" in source_meta:
                            manifest.category = source_meta["category"]

        return manifest if manifest.name else None
