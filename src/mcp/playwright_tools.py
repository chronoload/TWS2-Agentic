#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright CLI 增强模块 - TS2 爬虫系统升级
整合 playwright-cli-main 的 token-efficient 浏览器自动化能力

核心特性：
- Token-efficient snapshot：提取页面结构而非完整 HTML
- 元素引用系统：通过 e1, e2... refs 操作元素
- 多会话管理：持久化 profile、cookies、localStorage
- MCP 工具集成：为 AI Agent 提供浏览器控制能力
- SKILL 系统：本地参考文档驱动自动化
"""

import json
import asyncio
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
import threading
import re

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)


@dataclass
class SnapshotElement:
    """快照中的单个元素"""
    ref: str                    # 元素引用，如 "e1", "e2"
    tag: str                    # HTML 标签名
    role: str                   # ARIA role
    name: str                   # 可访问名称/文本内容
    value: str = ""             # 输入值
    expanded: bool = False      # 是否展开
    focused: bool = False       # 是否聚焦
    children: List['SnapshotElement'] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        d = {"ref": self.ref, "tag": self.tag, "role": self.role, "name": self.name}
        if self.value:
            d["value"] = self.value
        if self.expanded:
            d["expanded"] = True
        if self.focused:
            d["focused"] = True
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class PageSnapshot:
    """页面的 token-efficient 快照"""
    url: str
    title: str
    elements: List[SnapshotElement]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    
    def to_yaml_text(self) -> str:
        """生成 YAML 格式的快照文本（参考 playwright-cli-main）"""
        lines = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            f"Viewport: {self.viewport['width']}x{self.viewport['height']}",
            f"Timestamp: {self.timestamp}",
            "---",
            "# Page Elements (refs for interaction)",
        ]
        
        def render_element(elem: SnapshotElement, indent: int = 0) -> List[str]:
            prefix = "  " * indent
            line = f"{prefix}{elem.ref}: <{elem.tag}> [{elem.role}]"
            if elem.name:
                line += f" \"{elem.name[:80]}\""
            if elem.value:
                line += f" value=\"{elem.value[:50]}\""
            
            result = [line]
            for child in elem.children:
                result.extend(render_element(child, indent + 1))
            return result
        
        for elem in self.elements:
            lines.extend(render_element(elem))
        
        return "\n".join(lines)
    
    def get_element_refs(self) -> Dict[str, SnapshotElement]:
        """扁平化所有元素为 ref -> element 映射"""
        refs = {}
        
        def collect(e: SnapshotElement):
            refs[e.ref] = e
            for child in e.children:
                collect(child)
        
        for elem in self.elements:
            collect(elem)
        
        return refs


@dataclass
class BrowserSession:
    """浏览器会话状态"""
    session_id: str
    profile_name: Optional[str] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    snapshot: Optional[PageSnapshot] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def touch(self):
        self.last_activity = datetime.now().isoformat()


class PlaywrightCLITools:
    """
    Playwright CLI 增强工具集
    
    将 playwright-cli-main 的核心功能集成到 TS2 爬虫系统：
    - snapshot + refs 系统（token-efficient 页面结构）
    - 元素操作（click, type, select, press）
    - 多会话管理（持久化 profile、cookies）
    - 导航控制（goto, back, forward, reload）
    """
    
    def __init__(self, sessions_dir: Optional[Path] = None, headless: bool = True):
        self.sessions_dir = sessions_dir or Path(__file__).parent.parent / "playwright_sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        self._sessions: Dict[str, BrowserSession] = {}
        self._ref_counter = 0
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = threading.Lock()
        
        if not HAS_PLAYWRIGHT:
            logger.warning("Playwright 未安装，请运行: pip install playwright && playwright install")
    
    async def _ensure_browser(self) -> Browser:
        """确保浏览器已启动"""
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ]
            )
            logger.info("Playwright 浏览器已启动")
        return self._browser
    
    async def create_session(self, session_id: str = None, profile_name: str = None, 
                              load_cookies: bool = True) -> str:
        """创建新的浏览器会话"""
        session_id = session_id or f"session_{int(time.time())}"
        
        with self._lock:
            if session_id in self._sessions:
                return session_id
            
            browser = await self._ensure_browser()
            
            context_options = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "locale": "zh-CN",
            }
            
            # 持久化 profile
            if profile_name:
                storage_path = self.sessions_dir / f"{profile_name}.json"
                if storage_path.exists() and load_cookies:
                    try:
                        with open(storage_path, "r", encoding="utf-8") as f:
                            storage_state = json.load(f)
                        context_options["storage_state"] = storage_state
                        logger.info(f"已加载 profile: {profile_name}")
                    except Exception as e:
                        logger.warning(f"加载 profile 失败: {e}")
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            session = BrowserSession(
                session_id=session_id,
                profile_name=profile_name,
                context=context,
                page=page,
            )
            self._sessions[session_id] = session
            logger.info(f"会话已创建: {session_id}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """获取浏览器会话"""
        return self._sessions.get(session_id)
    
    async def close_session(self, session_id: str, save_cookies: bool = True):
        """关闭浏览器会话"""
        session = self._sessions.pop(session_id, None)
        if session and session.context:
            if save_cookies and session.profile_name:
                try:
                    storage_path = self.sessions_dir / f"{session.profile_name}.json"
                    state = await session.context.storage_state()
                    with open(storage_path, "w", encoding="utf-8") as f:
                        json.dump(state, f, indent=2)
                    logger.info(f"已保存 cookies: {session.profile_name}")
                except Exception as e:
                    logger.warning(f"保存 cookies 失败: {e}")
            
            await session.context.close()
            logger.info(f"会话已关闭: {session_id}")
    
    async def navigate(self, session_id: str, url: str, wait_until: str = "domcontentloaded") -> bool:
        """导航到 URL"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False
        
        try:
            await session.page.goto(url, wait_until=wait_until, timeout=30000)
            session.touch()
            return True
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False
    
    async def snapshot(self, session_id: str) -> Optional[PageSnapshot]:
        """
        生成页面的 token-efficient 快照
        
        参考 playwright-cli-main 的实现：
        - 只提取结构化信息，不返回完整 HTML
        - 为每个元素生成唯一的 ref（e1, e2, e3...）
        - 包含 ARIA role、名称、值等交互所需信息
        """
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return None
        
        try:
            # 重置 ref 计数器
            self._ref_counter = 0
            
            # 在页面中执行 JS 提取结构化信息
            elements_js = """() => {
                const elements = [];
                let refCounter = 0;
                
                function nextRef() {
                    refCounter++;
                    return 'e' + refCounter;
                }
                
                function getRole(el) {
                    const role = el.getAttribute('role');
                    if (role) return role;
                    
                    const tag = el.tagName.toLowerCase();
                    const roleMap = {
                        'a': 'link', 'button': 'button', 'input': 'textbox',
                        'select': 'combobox', 'textarea': 'textbox',
                        'img': 'img', 'h1': 'heading', 'h2': 'heading',
                        'h3': 'heading', 'h4': 'heading', 'h5': 'heading',
                        'h6': 'heading', 'p': 'paragraph', 'div': 'group',
                        'span': 'text', 'li': 'listitem', 'ul': 'list',
                        'ol': 'list', 'form': 'form', 'nav': 'navigation',
                        'main': 'main', 'header': 'banner', 'footer': 'contentinfo',
                        'article': 'article', 'section': 'region',
                        'table': 'table', 'tr': 'row', 'td': 'cell',
                        'th': 'columnheader', 'fieldset': 'group',
                        'legend': 'text', 'label': 'label',
                    };
                    return roleMap[tag] || tag;
                }
                
                function getName(el, role) {
                    // 优先使用 aria-label
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) return ariaLabel.trim();
                    
                    // 使用 alt/title
                    const alt = el.getAttribute('alt');
                    if (alt) return alt.trim();
                    const title = el.getAttribute('title');
                    if (title) return title.trim();
                    
                    // 对于 heading/paragraph，使用文本内容
                    if (['heading', 'paragraph', 'text', 'link', 'button'].includes(role)) {
                        const text = (el.innerText || el.textContent || '').trim();
                        return text.substring(0, 200);
                    }
                    
                    // 对于 input，使用 placeholder 或 name
                    if (role === 'textbox' || role === 'combobox') {
                        const placeholder = el.getAttribute('placeholder');
                        if (placeholder) return placeholder.trim();
                        const name = el.getAttribute('name');
                        if (name) return name;
                    }
                    
                    return '';
                }
                
                function isInteractive(el) {
                    const tag = el.tagName.toLowerCase();
                    const interactiveTags = ['a', 'button', 'input', 'select', 'textarea'];
                    if (interactiveTags.includes(tag)) return true;
                    if (el.getAttribute('role')) return true;
                    if (el.onclick || el.getAttribute('tabindex') !== null) return true;
                    return false;
                }
                
                function extractElement(el, maxDepth = 4, currentDepth = 0) {
                    if (currentDepth > maxDepth) return null;
                    
                    const role = getRole(el);
                    const name = getName(el, role);
                    
                    // 跳过无意义的元素
                    if (!name && !isInteractive(el) && role === 'group') {
                        return null;
                    }
                    
                    const ref = nextRef();
                    const result = {
                        ref,
                        tag: el.tagName.toLowerCase(),
                        role,
                        name,
                    };
                    
                    // 输入值
                    if (el.value !== undefined && el.value) {
                        result.value = String(el.value).substring(0, 100);
                    }
                    
                    // 状态
                    if (el.hasAttribute('aria-expanded')) {
                        result.expanded = el.getAttribute('aria-expanded') === 'true';
                    }
                    if (document.activeElement === el) {
                        result.focused = true;
                    }
                    
                    // 子元素（递归提取有意义的子元素）
                    const children = [];
                    for (const child of el.children) {
                        const childEl = extractElement(child, maxDepth, currentDepth + 1);
                        if (childEl) {
                            children.push(childEl);
                        }
                    }
                    if (children.length > 0) {
                        result.children = children;
                    }
                    
                    return result;
                }
                
                // 从 body 开始提取
                const bodyEl = document.body;
                const root = extractElement(bodyEl);
                return root;
            }"""
            
            root_element = await session.page.evaluate(elements_js)
            if not root_element:
                return None
            
            # 转换为 PageSnapshot
            def build_elements(data: dict) -> List[SnapshotElement]:
                elements = []
                
                def convert(d: dict) -> SnapshotElement:
                    elem = SnapshotElement(
                        ref=d.get("ref", ""),
                        tag=d.get("tag", ""),
                        role=d.get("role", ""),
                        name=d.get("name", ""),
                        value=d.get("value", ""),
                        expanded=d.get("expanded", False),
                        focused=d.get("focused", False),
                    )
                    for child_data in d.get("children", []):
                        elem.children.append(convert(child_data))
                    return elem
                
                # 根元素的子元素作为顶层元素
                for child_data in root_element.get("children", []):
                    elements.append(convert(child_data))
                
                return elements
            
            snapshot = PageSnapshot(
                url=session.page.url,
                title=await session.page.title(),
                elements=build_elements(root_element),
                viewport={"width": 1280, "height": 720},
            )
            
            session.snapshot = snapshot
            session.touch()
            return snapshot
            
        except Exception as e:
            logger.error(f"快照生成失败: {e}")
            return None
    
    async def click(self, session_id: str, ref: str) -> Tuple[bool, str]:
        """通过 ref 点击元素"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False, "会话不存在"
        
        # 生成 ref 映射
        ref_map = await self._build_ref_map(session)
        target = ref_map.get(ref)
        if not target:
            return False, f"元素 ref '{ref}' 不存在"
        
        try:
            await target.click()
            session.touch()
            
            # 点击后自动生成新快照
            new_snapshot = await self.snapshot(session_id)
            return True, f"已点击 {ref}"
        except Exception as e:
            return False, f"点击失败: {e}"
    
    async def type_text(self, session_id: str, ref: str, text: str) -> Tuple[bool, str]:
        """通过 ref 在输入框中输入文本"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False, "会话不存在"
        
        ref_map = await self._build_ref_map(session)
        target = ref_map.get(ref)
        if not target:
            return False, f"元素 ref '{ref}' 不存在"
        
        try:
            await target.click()
            await target.fill(text)
            session.touch()
            return True, f"已输入: {text[:50]}"
        except Exception as e:
            return False, f"输入失败: {e}"
    
    async def press_key(self, session_id: str, key: str) -> Tuple[bool, str]:
        """按下键盘按键"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False, "会话不存在"
        
        try:
            await session.page.keyboard.press(key)
            session.touch()
            return True, f"已按键: {key}"
        except Exception as e:
            return False, f"按键失败: {e}"
    
    async def select_option(self, session_id: str, ref: str, value: str) -> Tuple[bool, str]:
        """选择下拉选项"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False, "会话不存在"
        
        ref_map = await self._build_ref_map(session)
        target = ref_map.get(ref)
        if not target:
            return False, f"元素 ref '{ref}' 不存在"
        
        try:
            await target.select_option(value)
            session.touch()
            return True, f"已选择: {value}"
        except Exception as e:
            return False, f"选择失败: {e}"
    
    async def screenshot(self, session_id: str, output_path: Optional[str] = None) -> Optional[bytes]:
        """页面截图"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return None
        
        try:
            screenshot = await session.page.screenshot(full_page=True)
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(screenshot)
            session.touch()
            return screenshot
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None
    
    async def get_text(self, session_id: str, ref: str) -> Tuple[bool, str]:
        """获取元素文本内容"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False, "会话不存在"
        
        ref_map = await self._build_ref_map(session)
        target = ref_map.get(ref)
        if not target:
            return False, f"元素 ref '{ref}' 不存在"
        
        try:
            text = await target.inner_text()
            return True, text
        except Exception as e:
            return False, f"获取文本失败: {e}"
    
    async def wait_for_selector(self, session_id: str, selector: str, timeout: int = 10000) -> bool:
        """等待元素出现"""
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False
        
        try:
            await session.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False
    
    async def _build_ref_map(self, session: BrowserSession) -> Dict[str, Any]:
        """
        构建 ref -> element 映射
        
        通过在当前页面的快照中查找 ref 对应的 DOM 元素
        """
        if not session.page:
            return {}
        
        ref_map = {}
        snapshot = session.snapshot
        
        if not snapshot:
            return ref_map
        
        all_refs = snapshot.get_element_refs()
        
        # 通过 ref 在页面中查找元素
        for ref, elem in all_refs.items():
            # 使用元素的 tag、role、name 构建选择器
            selector = self._build_selector(elem)
            if selector:
                try:
                    el = await session.page.query_selector(selector)
                    if el:
                        ref_map[ref] = el
                except Exception:
                    pass
        
        return ref_map
    
    def _build_selector(self, elem: SnapshotElement) -> str:
        """根据元素信息构建 CSS 选择器"""
        parts = [elem.tag]
        
        if elem.name:
            # 尝试 aria-label 匹配
            return f'{elem.tag}[aria-label="{elem.name}"]'
        
        # 回退到 tag
        return elem.tag
    
    async def cleanup(self):
        """清理所有会话和浏览器"""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.close_session(sid, save_cookies=True)
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        logger.info("Playwright 资源已清理")


# ===================== MCP 工具集成 =====================

class PlaywrightToolProvider:
    """
    为 TS2 MCP Agent 系统提供 Playwright 浏览器自动化工具
    
    将 PlaywrightCLITools 封装为 MCP 工具格式，使 AI Agent 能够通过
    标准工具接口控制浏览器。
    """
    
    def __init__(self, cli_tools: PlaywrightCLITools = None, sessions_dir: Path = None, headless: bool = True):
        self.cli_tools = cli_tools or PlaywrightCLITools(sessions_dir=sessions_dir, headless=headless)
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回 MCP 工具定义列表"""
        return [
            {
                "name": "browser_create_session",
                "description": "创建新的浏览器会话（支持持久化 profile、cookies）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID（可选，默认自动生成）"},
                        "profile_name": {"type": "string", "description": "Profile 名称（用于持久化 cookies）"},
                    },
                    "required": [],
                },
            },
            {
                "name": "browser_navigate",
                "description": "导航到指定 URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "url": {"type": "string", "description": "目标 URL"},
                    },
                    "required": ["session_id", "url"],
                },
            },
            {
                "name": "browser_snapshot",
                "description": "生成页面的 token-efficient 快照，返回结构化元素和 refs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "browser_click",
                "description": "通过 ref 点击页面元素",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "ref": {"type": "string", "description": "元素引用（如 e1, e2）"},
                    },
                    "required": ["session_id", "ref"],
                },
            },
            {
                "name": "browser_type",
                "description": "通过 ref 在输入框中输入文本",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "ref": {"type": "string", "description": "元素引用"},
                        "text": {"type": "string", "description": "输入的文本"},
                    },
                    "required": ["session_id", "ref", "text"],
                },
            },
            {
                "name": "browser_press",
                "description": "按下键盘按键（如 Enter, Escape, ArrowDown）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "key": {"type": "string", "description": "按键名称"},
                    },
                    "required": ["session_id", "key"],
                },
            },
            {
                "name": "browser_screenshot",
                "description": "页面截图",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "output_path": {"type": "string", "description": "保存路径（可选）"},
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "browser_close_session",
                "description": "关闭浏览器会话（可选择保存 cookies）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "save_cookies": {"type": "boolean", "description": "是否保存 cookies"},
                    },
                    "required": ["session_id"],
                },
            },
        ]
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """执行指定的浏览器工具"""
        try:
            if tool_name == "browser_create_session":
                session_id = await self.cli_tools.create_session(
                    session_id=kwargs.get("session_id"),
                    profile_name=kwargs.get("profile_name"),
                )
                return {"success": True, "session_id": session_id}
            
            elif tool_name == "browser_navigate":
                success = await self.cli_tools.navigate(
                    session_id=kwargs["session_id"],
                    url=kwargs["url"],
                )
                return {"success": success}
            
            elif tool_name == "browser_snapshot":
                snapshot = await self.cli_tools.snapshot(session_id=kwargs["session_id"])
                if snapshot:
                    return {
                        "success": True,
                        "url": snapshot.url,
                        "title": snapshot.title,
                        "element_count": len(snapshot.get_element_refs()),
                        "yaml": snapshot.to_yaml_text(),
                    }
                return {"success": False, "error": "快照生成失败"}
            
            elif tool_name == "browser_click":
                success, message = await self.cli_tools.click(
                    session_id=kwargs["session_id"],
                    ref=kwargs["ref"],
                )
                return {"success": success, "message": message}
            
            elif tool_name == "browser_type":
                success, message = await self.cli_tools.type_text(
                    session_id=kwargs["session_id"],
                    ref=kwargs["ref"],
                    text=kwargs["text"],
                )
                return {"success": success, "message": message}
            
            elif tool_name == "browser_press":
                success, message = await self.cli_tools.press_key(
                    session_id=kwargs["session_id"],
                    key=kwargs["key"],
                )
                return {"success": success, "message": message}
            
            elif tool_name == "browser_screenshot":
                screenshot = await self.cli_tools.screenshot(
                    session_id=kwargs["session_id"],
                    output_path=kwargs.get("output_path"),
                )
                return {"success": screenshot is not None}
            
            elif tool_name == "browser_close_session":
                await self.cli_tools.close_session(
                    session_id=kwargs["session_id"],
                    save_cookies=kwargs.get("save_cookies", True),
                )
                return {"success": True}
            
            else:
                return {"success": False, "error": f"未知工具: {tool_name}"}
        
        except Exception as e:
            logger.error(f"工具执行失败 {tool_name}: {e}")
            return {"success": False, "error": str(e)}


# ===================== 便捷函数 =====================

def get_playwright_tools(sessions_dir: Path = None, headless: bool = True) -> PlaywrightToolProvider:
    """获取 Playwright 工具提供者单例"""
    return PlaywrightToolProvider(sessions_dir=sessions_dir, headless=headless)


if __name__ == "__main__":
    # 测试
    async def test():
        tools = get_playwright_tools()
        
        # 创建会话
        session_id = await tools.cli_tools.create_session("test_session")
        print(f"会话创建: {session_id}")
        
        # 导航
        success = await tools.cli_tools.navigate(session_id, "https://example.com")
        print(f"导航: {success}")
        
        # 快照
        snapshot = await tools.cli_tools.snapshot(session_id)
        if snapshot:
            print(f"快照: {snapshot.url} - {snapshot.title}")
            print(f"元素数量: {len(snapshot.get_element_refs())}")
            print("\n--- YAML 快照 ---")
            print(snapshot.to_yaml_text())
        
        # 关闭
        await tools.cli_tools.close_session(session_id)
        await tools.cli_tools.cleanup()
        print("\n测试完成")
    
    if HAS_PLAYWRIGHT:
        asyncio.run(test())
    else:
        print("Playwright 未安装，跳过测试")
