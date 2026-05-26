#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI 状态持久化 — 窗口几何、主题、分屏、滚动位置
参考 Cline webview state + OpenCode tui state 设计
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path

from .disk import get_disk_store
from .state_manager import get_state_manager

import logging
logger = logging.getLogger(__name__)


@dataclass
class WindowGeometry:
    window_id: str
    x: int = 100
    y: int = 100
    width: int = 450
    height: int = 700
    maximized: bool = False
    visible: bool = True
    last_opened: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "WindowGeometry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class UIState:
    theme: str = "light"
    font_family: str = "Consolas"
    font_size: int = 9
    sidebar_width: int = 250
    sidebar_visible: bool = True
    active_tab: str = ""
    notebook_tab: str = ""
    scroll_position: float = 0.0
    selected_conversation_id: str = ""
    auto_scroll: bool = True
    show_line_numbers: bool = True
    word_wrap: bool = True
    recent_files: List[str] = field(default_factory=list)
    recent_searches: List[str] = field(default_factory=list)
    expanded_sections: List[str] = field(default_factory=list)
    pane_sizes: Dict[str, int] = field(default_factory=dict)
    window_states: Dict[str, WindowGeometry] = field(default_factory=dict)
    custom_styles: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["window_states"] = {
            k: v.to_dict() if isinstance(v, WindowGeometry) else v
            for k, v in d.get("window_states", {}).items()
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "UIState":
        window_states = {}
        for k, v in d.get("window_states", {}).items():
            window_states[k] = WindowGeometry.from_dict(v) if isinstance(v, dict) else v
        d["window_states"] = window_states
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class UIStateManager:
    """
    UI 状态管理器

    职责：
    - 窗口几何保存/恢复
    - 主题和字体状态
    - 标签页、滚动位置
    - 最近文件、搜索历史
    """

    def __init__(self):
        self._disk = get_disk_store()
        self._state_manager = get_state_manager()
        self._ui_state: Optional[UIState] = None
        self._dirty = False
        self._lock = __import__("threading").RLock()

    @property
    def state(self) -> UIState:
        if self._ui_state is None:
            self._load()
        return self._ui_state

    def _load(self):
        data = self._disk.ui_state_store.all()
        if data:
            self._ui_state = UIState.from_dict(data)
        else:
            self._ui_state = UIState()

    def _save(self):
        if self._ui_state:
            self._disk.ui_state_store.set_batch(self._ui_state.to_dict())
            self._dirty = False

    def save_window_geometry(self, window_id: str, x: int, y: int,
                              width: int, height: int, **kwargs):
        geom = WindowGeometry(
            window_id=window_id, x=x, y=y,
            width=width, height=height, **kwargs,
        )
        self.state.window_states[window_id] = geom
        self._dirty = True

    def get_window_geometry(self, window_id: str) -> Optional[WindowGeometry]:
        return self.state.window_states.get(window_id)

    def restore_window_geometry(self, window, window_id: str,
                                 default_width: int = 450,
                                 default_height: int = 700):
        """恢复到 tkinter 窗口"""
        geom = self.get_window_geometry(window_id)
        if geom and not geom.maximized:
            try:
                window.geometry(f"{geom.width}x{geom.height}+{geom.x}+{geom.y}")
                return True
            except Exception:
                pass
        try:
            window.geometry(f"{default_width}x{default_height}")
        except Exception:
            pass
        return False

    def save_theme(self, theme: str):
        self.state.theme = theme
        self._dirty = True

    def get_theme(self) -> str:
        return self.state.theme

    def save_font_config(self, family: str = "", size: int = 0):
        if family:
            self.state.font_family = family
        if size:
            self.state.font_size = size
        self._dirty = True

    def set_active_tab(self, tab_name: str):
        self.state.active_tab = tab_name
        self._dirty = True

    def get_active_tab(self) -> str:
        return self.state.active_tab

    def set_selected_conversation(self, conversation_id: str):
        self.state.selected_conversation_id = conversation_id
        self._dirty = True

    def add_recent_file(self, file_path: str, max_recent: int = 20):
        recent = self.state.recent_files
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        if len(recent) > max_recent:
            recent[:] = recent[:max_recent]
        self._dirty = True

    def get_recent_files(self) -> List[str]:
        return self.state.recent_files

    def add_recent_search(self, query: str, max_recent: int = 10):
        searches = self.state.recent_searches
        if query in searches:
            searches.remove(query)
        searches.insert(0, query)
        if len(searches) > max_recent:
            searches[:] = searches[:max_recent]
        self._dirty = True

    def get_recent_searches(self) -> List[str]:
        return self.state.recent_searches

    def save_pane_size(self, pane_name: str, size: int):
        self.state.pane_sizes[pane_name] = size
        self._dirty = True

    def get_pane_size(self, pane_name: str) -> int:
        return self.state.pane_sizes.get(pane_name, 200)

    def apply_theme_to_tk(self, root) -> str:
        theme = self.get_theme()
        if theme == "dark":
            root.tk_setPalette(background="#1e1e1e", foreground="#d4d4d4")
        return theme

    def persist(self):
        if self._dirty:
            self._save()


_ui_state_manager: Optional[UIStateManager] = None


def get_ui_state_manager() -> UIStateManager:
    global _ui_state_manager
    if _ui_state_manager is None:
        _ui_state_manager = UIStateManager()
    return _ui_state_manager