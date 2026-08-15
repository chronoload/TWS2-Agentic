#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_search.py — 会话全文搜索（rg 加速 + Python 回退）

复用 rg_search 模块的 ripgrep 加速能力（系统已装 rg 15.1.0），
在会话存储目录（cache_data/sessions/*.json）全文搜索关键词：
匹配会话名称 + 全部消息内容。rg 不可用/出错时回退 Python 字面量遍历，
两路共用同一过滤语义，结果一致（参考 sync.py 的 rg 加速模式）。

对外函数：
  search_session_ids(store_dir, kw) → Optional[Set[str]]
      - 返回匹配的 session_id 集合
      - None 表示无法判定（调用方应保留全部）
      - kw 为空 → 返回 None（不筛选）
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

# rg --json 输出行: 'C:\path\sess_x.json:12: content'
# 提取 .json 文件路径（Windows 盘符冒号不干扰：从第一个 .json 前的非冒号字符段匹配）
_JSON_PATH_RE = re.compile(r"([^:\r\n]+\.json):\d+:", re.IGNORECASE)


def search_session_ids(store_dir: str, kw: str) -> Optional[Set[str]]:
    """在会话存储目录全文搜索关键词（名称 + 消息内容）。

    Args:
        store_dir: 会话存储目录（SessionStore.store_dir）
        kw: 搜索关键词

    Returns:
        - 匹配的 session_id 集合
        - 空集表示无匹配
        - None 表示无法判定（存储不可用/搜索不可行，调用方保留全部）
    """
    sdir = Path(store_dir)
    kw = (kw or "").strip()
    if not kw:
        return None
    if not sdir.exists():
        return set()

    # ── rg 加速路径（零新增依赖，毫秒级）──
    try:
        from ..rg_search import rg_grep
        # re.escape 保证用户输入按字面量搜（与 Python 回退一致；rg 把 pattern 当正则）
        result = rg_grep(
            re.escape(kw),
            str(sdir),
            ignore_case=True,
            max_results=5000,
            globs=["*.json"],
            timeout=10.0,
        )
        if result is not None:
            _, _, lines = result
            ids: Set[str] = set()
            for ln in lines:
                m = _JSON_PATH_RE.search(ln)
                if m:
                    stem = Path(m.group(1)).stem
                    if stem:
                        ids.add(stem)
            return ids
    except Exception as e:
        logger.debug("session search rg 回退 Python: %s", e)

    # ── Python 回退：字面量遍历（名称 + 消息内容）──
    ids = set()
    low = kw.lower()
    try:
        for f in sdir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("name", "") or ""
                msgs = data.get("messages", [])
                text = name + " " + json.dumps(msgs, ensure_ascii=False)
                if low in text.lower():
                    ids.add(f.stem)
            except Exception:
                continue
        return ids
    except Exception as e:
        logger.debug("session search Python 回退失败: %s", e)
        return None
