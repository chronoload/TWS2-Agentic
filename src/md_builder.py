#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown Syllabus 解析器 (TS2 适配版)
======================================
将 Markdown 格式 Syllabus 文件解析为符合 TS2 courses_structured.json 格式的课程数据。

支持三种 MD 表格格式：
  格式A：| 课时编号 | 标题 | 主题主要内容 | 描述 |
  格式B：| 全局课时 | 课时标题 | 主题/主要内容 | 描述 | 参考资料 |
  格式C：| 课时序号 | 所属Section | 课时标题 | ... |（Section标题嵌在表格行内）

用法:
  python md_builder.py path/to/syllabus.md --output result.json
  python md_builder.py --dir Courses/1/notes_md/
"""

import re
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# ─── 学科域关键词映射 ────────────────────────────────────────────────
DOMAIN_KEYWORDS = {
    'P': {'name': '系统物理域', 'kw': ['物理', '力学', '电磁', '量子', '相对论', '统计物理', '电动力学',
              '热力学', '光学', '场论', '分析物理', '理论物理', '软物质']},
    'A': {'name': '代数学域', 'kw': ['代数', '群论', '环', '域', '模', '线性代数', '抽象代数', '综合代数']},
    'N': {'name': '分析学域', 'kw': ['分析', '微积分', '实分析', '复分析', '泛函', '测度', '拓扑']},
    'C': {'name': '范畴论域', 'kw': ['范畴', '函子', '自然变换', '伴随', '极限']},
    'M': {'name': '建模与计算域', 'kw': ['建模', '机器学习', '优化', '数值计算', '模拟', '蒙特卡洛',
              '回归', '分类', '聚类', '深度学习', '神经网络', '统计学习', '数据驱动',
              '数学建模', '线性规划', '整数规划', '微分方程', '插值', '拟合']},
    'S': {'name': '合成生信域', 'kw': ['合成生物', '生物信息', '系统生物', '分子生物', '基因',
              '蛋白质', '组学', '基因组', '转录组', '代谢组', '生物网络', '基因线路',
              '细胞生物', '生化', '生物物理', 'DNA', 'RNA', 'PCR', '测序']},
    'BIO': {'name': '生物信息域', 'kw': ['生物信息', '组学', '基因组', '转录组', '蛋白组', '代谢组',
              '序列分析', '比对', '数据库', '注释', '通路']},
    'CS': {'name': '计算机系统域', 'kw': ['计算机系统', '组成原理', '体系结构', '操作系统', '编译',
              '实时', '并行', '嵌入式']},
    'SE': {'name': '软件工程域', 'kw': ['软件工程', '系统设计', '软件架构', '设计模式', '敏捷']},
    'DS': {'name': '数据结构与算法域', 'kw': ['数据结构', '算法', '排序', '图论', '动态规划', '搜索算法']},
    'DE': {'name': '数字电路与嵌入式域', 'kw': ['数字电路', '嵌入式', 'STM32', 'ARM', 'FPGA', '单片机',
              'Verilog', 'Cortex', 'GPIO', 'UART', 'PWM', 'SPI', 'I2C']},
    'LM': {'name': '逻辑与数学基础域', 'kw': ['逻辑', '证明', '集合论', '数理逻辑']},
    'D': {'name': '离散结构域', 'kw': ['离散数学', '组合', '图论', '计数', '排列组合']},
}


def classify_domain(title, content_sample=""):
    """根据标题和内容样本推断学科域"""
    text = (title + " " + content_sample).lower()
    best, best_score = "UNKNOWN", 0
    for domain, info in DOMAIN_KEYWORDS.items():
        keywords = info['kw']
        score = sum(2 if k in title else 1 for k in keywords if k in text)
        if score > best_score:
            best, best_score = domain, score
    return best


def generate_note_id(filepath, title):
    """从文件名提取 note_id，或基于标题生成"""
    # 尝试从文件名前缀提取数字ID
    m = re.match(r'^(\d+)_', Path(filepath).stem)
    if m:
        return m.group(1)
    # 基于标题生成
    h = hashlib.md5(title.encode('utf-8')).hexdigest()[:16]
    return f"md_{h}"


# ─── 解析器核心 ───────────────────────────────────────────────────────

class MDSyllabusParser:
    """Markdown 格式 Syllabus 解析器"""

    @staticmethod
    def _clean_html(text):
        """清理 HTML 标签和常见实体"""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = re.sub(r'&#x?[0-9A-Fa-f]+;?', '', text)  # &#xA; &#160; etc.
        return text.strip()

    SECTION_RE = re.compile(
        r'^#{2,3}\s*Section\s*(\d+)[：:]\s*(.+?)(?:\s*[\(（]'
        r'(?:课时\s*\d+[-–]\d+[，,]\s*)?共?\s*(\d+)\s*课时'
        r'[\)）])?\s*$',
        re.MULTILINE
    )

    SECTION_RE2 = re.compile(
        r'^#{2,3}\s*Section\s*(\d+)\s*[：:]?\s*(.*?)$',
        re.MULTILINE
    )

    LESSON_NUM_RE = re.compile(r'^\|?\s*([Ss]\d+-)?(\d+)\s*\|')
    TITLE_RE = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)
    HOURS_RE = re.compile(r'(\d+)\s*课时')
    PREREQ_RE = re.compile(r'先修[要求课程：:]*\s*(.+?)(?:\s*[\|｜]|\s*$)')

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.text = self._read()
        self.filename = self.filepath.stem

    def _read(self):
        encodings = ['utf-8', 'gbk', 'gb18030', 'utf-16']
        for enc in encodings:
            try:
                return self.filepath.read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return self.filepath.read_text(encoding='utf-8', errors='replace')

    def parse(self):
        """解析 MD 文件，返回符合 TS2 格式的课程 dict"""
        title = self._extract_title()
        total_hours = self._extract_total_hours()
        prerequisites = self._extract_prerequisites()
        sections, lessons = self._extract_structure()
        domain = classify_domain(title, self.text[:3000])

        # 文件名中的课时信息最可靠
        fn_match = re.search(r'[（(](\d+)\s*课时[）)]', self.filename)
        if fn_match:
            total_hours = int(fn_match.group(1))
        elif total_hours is None:
            section_hours_sum = sum(s.get('section_hours', 0) or 0 for s in sections)
            if section_hours_sum > 0:
                total_hours = section_hours_sum

        note_id = generate_note_id(self.filepath, title)

        course = {
            "filename": self.filepath.name,
            "note_id": note_id,
            "course_title": title,
            "total_hours": total_hours,
            "prerequisites": prerequisites,
            "sections": sections,
            "lessons": lessons,
            "references": self._extract_references(),
            "domain": domain,
            "domain_name": DOMAIN_KEYWORDS.get(domain, {}).get('name', domain),
            "source_file": str(self.filepath),
            "source_type": "md",
        }
        return course

    def _extract_title(self):
        m = self.TITLE_RE.search(self.text)
        if m:
            t = m.group(1).strip()
            t = re.sub(r'^#+\s*', '', t).strip()
            t = re.sub(r'\s*Syllabus\s*', ' ', t, flags=re.IGNORECASE).strip()
            t = re.sub(r'\s*课程\s*Syllabus\s*', ' ', t, flags=re.IGNORECASE).strip()
            t = re.sub(r'[（(]\d+\s*课时[）)]', '', t).strip()
            t = re.sub(r'[（(]\s*Syllabus\s*[）)]', '', t).strip()
            t = re.sub(r'[（(]\s*共?\s*\d+\s*课时[）)]', '', t).strip()
            t = re.sub(r'[（(]\s*总?\s*\d+\s*课时.*?[）)]', '', t).strip()
            t = re.sub(r'\s*[|｜]\s*$', '', t).strip()
            t = re.sub(r'\s*[|｜]\s*', ' ', t).strip()
            t = re.sub(r'\s*补充参考资料标注版\s*', '', t).strip()
            t = re.sub(r'\s*参考资料来源标注版\s*', '', t).strip()
            t = re.sub(r'\s*_?\s*参考资料标注版\s*', '', t).strip()
            t = re.sub(r'\s*[（(]\s*[）)]\s*$', '', t).strip()
            if t:
                return t

        name = self.filename
        name = re.sub(r'^\d+_', '', name)
        name = re.sub(r'[（(]\d+\s*课时[）)]', '', name).strip()
        name = re.sub(r'[（(]\s*Syllabus\s*[）)]', '', name).strip()
        name = re.sub(r'[（(]\s*共?\s*\d+\s*课时.*?[）)]', '', name).strip()
        return name if name else "未知课程"

    def _extract_total_hours(self):
        head = self.text[:1500]
        m = re.search(r'总课时[：:]\s*(\d+)\s*课时', head)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*课时\s*[|｜]', head)
        if m:
            return int(m.group(1))
        return None

    def _extract_prerequisites(self):
        head = self.text[:2000]
        m = self.PREREQ_RE.search(head)
        if m:
            raw = m.group(1).strip()
            parts = re.split(r'[，,、；;]', raw)
            return [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
        return []

    def _extract_structure(self):
        sections = []
        lessons = []

        section_blocks = self._split_sections()

        # 清除上一次解析可能留下的表格内嵌 Section 信息
        self._table_section_info = {}

        for block_idx, (sec_header, block_text) in enumerate(section_blocks):
            sec_info = self._parse_section_header(sec_header, block_idx + 1)
            block_lessons = self._parse_lessons_from_table(block_text, sec_info['section_number'])
            sec_info['lesson_range'] = self._lesson_range(block_lessons)
            if not sec_info.get('section_hours') and block_lessons:
                sec_info['section_hours'] = len(block_lessons)
            sections.append(sec_info)
            lessons.extend(block_lessons)

        # 获取表格内嵌的 Section 信息
        table_sec_info = getattr(self, '_table_section_info', {})

        # 按"所属Section"列或课时编号重新分组
        if len(sections) <= 1 and lessons:
            section_map = {}
            for l in lessons:
                sn = l.get('section', 0)
                if sn not in section_map:
                    section_map[sn] = []
                section_map[sn].append(l)
            if len(section_map) > 1:
                sections = []
                for sn in sorted(section_map.keys()):
                    sec_lessons = section_map[sn]
                    # 使用表格内嵌的 Section 标题信息（如有）
                    sec_title = f'Section {sn}'
                    sec_hours = len(sec_lessons)
                    if sn in table_sec_info:
                        sec_title = table_sec_info[sn].get('title', sec_title)
                        if table_sec_info[sn].get('hours'):
                            sec_hours = table_sec_info[sn]['hours']
                    sections.append({
                        'section_number': sn,
                        'section_title': sec_title,
                        'section_hours': sec_hours,
                        'lesson_range': self._lesson_range(sec_lessons),
                    })

        self._enrich_section_titles(sections)
        return sections, lessons

    def _enrich_section_titles(self, sections):
        pattern = re.compile(
            r'\|\s*#{2,3}\s*Section\s*(\d+)\s+(.+?)'
            r'(?:\s*[\(（](\d+)\s*课时[\)）])?\s*\|',
            re.MULTILINE
        )
        for m in pattern.finditer(self.text):
            sn = int(m.group(1))
            title = m.group(2).strip()
            hours = int(m.group(3)) if m.group(3) else None
            for s in sections:
                if s['section_number'] == sn and (not s['section_title'] or s['section_title'].startswith('Section ')):
                    s['section_title'] = title
                    if hours:
                        s['section_hours'] = hours
                    break

    def _split_sections(self):
        blocks = []
        matches = list(self.SECTION_RE.finditer(self.text))
        if not matches:
            matches = list(self.SECTION_RE2.finditer(self.text))
        if not matches:
            return [("", self.text)]
        for i, m in enumerate(matches):
            header = m.group(0)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(self.text)
            block = self.text[start:end]
            blocks.append((header, block))
        return blocks

    def _parse_section_header(self, header, fallback_number):
        info = {
            "section_number": fallback_number,
            "section_title": "",
            "section_hours": None,
        }
        patterns = [
            r'#{2,3}\s*Section\s*(\d+)\s*[：:]\s*(.+?)'
            r'(?:\s*[\(（](?:课时\s*\d+[-–]\d+[，,]\s*)?共?\s*(\d+)\s*课时[\)）])?\s*$',
            r'#{2,3}\s*Section\s*(\d+)\s*[：:]\s*(.+?)'
            r'(?:\s*[\(（]课时\s*\d+[-–]\d+[,，]\s*共?\s*(\d+)\s*课时[\)）])?\s*$',
            r'#{2,3}\s*Section\s*(\d+)\s+(.+?)'
            r'(?:\s*[\(（](\d+)\s*课时[\)）])?\s*$',
            r'#{2,3}\s*Section\s*(\d+)\s*[：:]?\s*(.*?)$',
        ]
        for pat in patterns:
            m = re.match(pat, header)
            if m:
                info['section_number'] = int(m.group(1))
                info['section_title'] = m.group(2).strip() if m.group(2) else ""
                if m.lastindex >= 3 and m.group(3):
                    info['section_hours'] = int(m.group(3))
                elif 'section_title' in info:
                    hm = re.search(r'(\d+)\s*课时', info['section_title'])
                    if hm:
                        info['section_hours'] = int(hm.group(1))
                        info['section_title'] = re.sub(r'\s*[\(（].*?\d+\s*课时.*?[\)）]', '', info['section_title']).strip()
                return info
        return info

    # 匹配表格第一列中的 Section 标题行，如 **Section 1 微积分基础（40课时）**
    _TABLE_SECTION_RE = re.compile(
        r'\*+\s*Section\s*(\d+)\s*[：:]\s*(.+?)\s*[\(（](\d+)\s*课时[\)）]\s*\*+',
        re.IGNORECASE
    )

    def _parse_lessons_from_table(self, block_text, section_number):
        lessons = []
        lines = block_text.split('\n')
        in_table = False
        header_parsed = False
        num_col_idx = 0
        title_col_idx = 1
        sec_col_idx = -1
        content_col_idx = -1
        desc_col_idx = -1
        ref_col_idx = -1
        global_numbering = False

        current_table_section = section_number
        table_section_info = {}
        prev_cell_count = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if '|' in stripped:
                cells = [c.strip() for c in stripped.split('|')]
                while cells and not cells[0]:
                    cells.pop(0)
                while cells and not cells[-1]:
                    cells.pop()
                if not cells:
                    continue

                if all(re.match(r'^[-–—:]+$', c) for c in cells if c):
                    in_table = True
                    header_parsed = True
                    continue

                if not header_parsed and any(k in stripped for k in
                        ['课时编号', '课时序号', '全局课时', '课时', '编号', '标题']):
                    for idx, c in enumerate(cells):
                        c_lower = c.lower()
                        if any(k in c_lower for k in ['编号', '序号', '课时编号', '全局课时']):
                            num_col_idx = idx
                        if '标题' in c_lower and '课时' not in c_lower:
                            title_col_idx = idx
                        if '课时标题' in c_lower:
                            title_col_idx = idx
                        if 'section' in c_lower or '所属' in c:
                            sec_col_idx = idx
                            global_numbering = True
                        if any(k in c_lower for k in ['主题', '主要内容', '内容']):
                            if '标题' not in c_lower:
                                content_col_idx = idx
                        if any(k in c_lower for k in ['描述', '说明', '详细', '核心']):
                            desc_col_idx = idx
                        if any(k in c_lower for k in ['参考', '资料', '文献', '教材']):
                            ref_col_idx = idx
                    header_parsed = True
                    in_table = True
                    prev_cell_count = len(cells)
                    continue

                if not in_table:
                    continue

                # 检测列数变化（可能某些 Section 少了 Section 列，导致列数不同）
                cur_cell_count = len(cells)
                if prev_cell_count > 0 and cur_cell_count != prev_cell_count and cur_cell_count >= 3:
                    # 列数变化，重新推断列索引
                    # 策略：根据第一列的内容判断格式
                    first_val = self._clean_html(cells[0]) if cells else ""
                    # 检查第一列是否像课时编号 (如 "1.1", "7.2", "23" 等)
                    if re.match(r'\d+(\.\d+)?$', first_val):
                        # 第一列是编号 → 4列格式: 编号 | 标题 | 内容 | 描述
                        num_col_idx = 0
                        title_col_idx = 1
                        remaining = cur_cell_count - 2
                        content_col_idx = 2 if remaining >= 1 else -1
                        desc_col_idx = 3 if remaining >= 2 else -1
                        ref_col_idx = 4 if remaining >= 3 else -1
                    else:
                        # 第一列不是编号 → 5列格式: Section | 编号 | 标题 | 内容 | 描述
                        num_col_idx = 1
                        title_col_idx = 2
                        remaining = cur_cell_count - 3
                        content_col_idx = 3 if remaining >= 1 else -1
                        desc_col_idx = 4 if remaining >= 2 else -1
                        ref_col_idx = 5 if remaining >= 3 else -1
                    prev_cell_count = cur_cell_count

                # 检查第一列是否为表格内嵌的 Section 标题行
                first_cell = cells[0] if cells else ""
                first_cell_clean = self._clean_html(first_cell)
                ts_match = self._TABLE_SECTION_RE.search(first_cell_clean)
                if not ts_match:
                    # 也检查课时编号列
                    num_cell = cells[num_col_idx].strip() if num_col_idx < len(cells) else ""
                    num_clean = self._clean_html(num_cell)
                    ts_match = self._TABLE_SECTION_RE.search(num_clean)
                if ts_match:
                    sn = int(ts_match.group(1))
                    st = ts_match.group(2).strip()
                    sh = int(ts_match.group(3)) if ts_match.group(3) else None
                    current_table_section = sn
                    table_section_info[sn] = {'title': st, 'hours': sh}
                    # 如果该行同时含课时数据（如 Section 1 行也有 1.1 课时），继续解析
                    # 否则跳过此行
                    num_str = cells[num_col_idx].strip() if num_col_idx < len(cells) else ""
                    if not self._parse_lesson_number(num_str):
                        continue

                if len(cells) > max(num_col_idx, title_col_idx):
                    num_str = cells[num_col_idx].strip() if num_col_idx < len(cells) else ""
                    title_str = cells[title_col_idx].strip() if title_col_idx < len(cells) else ""

                    if '## Section' in num_str or '## Section' in title_str:
                        continue

                    lesson_num = self._parse_lesson_number(
                        num_str, None if global_numbering else current_table_section)
                    if lesson_num is None:
                        continue

                    title_str = self._clean_html(title_str)
                    if not title_str or title_str in ('​', '&nbsp;'):
                        continue

                    actual_section = current_table_section
                    # 如果有"所属Section"列，优先使用
                    if sec_col_idx >= 0 and sec_col_idx < len(cells):
                        sec_str = cells[sec_col_idx].strip()
                        sec_m = re.search(r'Section\s*(\d+)', sec_str, re.IGNORECASE)
                        if sec_m:
                            actual_section = int(sec_m.group(1))

                    # 提取描述列内容
                    desc_text = ""
                    if desc_col_idx >= 0 and desc_col_idx < len(cells):
                        desc_text = self._clean_html(cells[desc_col_idx])

                    # 提取中心问题：优先从"描述"列提取（中心问题：xxx），其次从"主题/主要内容"列
                    central_question = ""
                    if desc_text:
                        cq_match = re.search(r'中心问题[：:]\s*(.+?)(?=[。；;]|核心定理|核心定义|实践任务|实践要求)', desc_text)
                        if cq_match:
                            central_question = cq_match.group(1).strip()[:200]
                    # 回退：从主题/主要内容列提取
                    if not central_question and content_col_idx >= 0 and content_col_idx < len(cells):
                        q = self._clean_html(cells[content_col_idx])
                        if q and q not in ('​', '&nbsp;') and len(q) > 2:
                            central_question = q[:200]

                    # 提取课时级参考资料
                    lesson_refs = []
                    if ref_col_idx >= 0 and ref_col_idx < len(cells):
                        ref_text = self._clean_html(cells[ref_col_idx])
                        if ref_text and ref_text not in ('​', '&nbsp;'):
                            # 按常见分隔符拆分
                            for part in re.split(r'[、，,；;]', ref_text):
                                part = part.strip()
                                if part and len(part) > 2:
                                    lesson_refs.append(part[:200])

                    lesson = {
                        "lesson_number": lesson_num,
                        "lesson_title": title_str,
                        "section": actual_section,
                    }
                    if desc_text and desc_text not in ('​', '&nbsp;'):
                        lesson["description"] = desc_text[:1000]
                    if central_question:
                        lesson["central_question"] = central_question
                    if lesson_refs:
                        lesson["references"] = lesson_refs
                    lessons.append(lesson)
            else:
                if stripped.startswith('##') or stripped.startswith('***'):
                    in_table = False
                    header_parsed = False
                    continue

        # 将表格内嵌的 Section 信息附加到返回的 lessons 上
        # 通过 _extract_structure 中的后续逻辑使用
        if table_section_info:
            # 存储为特殊属性，供 _extract_structure 使用
            self._table_section_info = table_section_info

        return lessons

    def _parse_lesson_number(self, num_str, section_hint=None):
        """解析课时编号，支持 X.Y 格式（如 1.1, 2.3）
        
        对于 X.Y 格式，返回 (section*1000 + Y) 以保证全局唯一。
        section_hint: 从表格上下文推断的 section 编号，用于纯数字编号。
        """
        # S1-3 格式
        m = re.match(r'[Ss](\d+)[-–](\d+)', num_str)
        if m:
            return int(m.group(1)) * 1000 + int(m.group(2))
        # X.Y 格式 (如 1.1, 2.3, 6.10)
        m = re.match(r'(\d+)\.(\d+)', num_str)
        if m:
            sec = int(m.group(1))
            lnum = int(m.group(2))
            return sec * 1000 + lnum
        # 纯数字格式 (如 1, 23, 40)
        m = re.match(r'(\d+)', num_str)
        if m:
            n = int(m.group(1))
            if n < 10000:
                # 如果有 section_hint，生成全局唯一编号
                if section_hint and section_hint > 0:
                    return section_hint * 1000 + n
                return n
        return None

    def _lesson_range(self, lessons):
        if not lessons:
            return ""
        nums = [l['lesson_number'] for l in lessons]
        return f"{min(nums)}-{max(nums)}"

    def _extract_references(self):
        refs = []
        ref_section = re.search(
            r'(?:核心)?参考资料[总览]*[：:\n](.+?)(?:\n##|\n\*\*\*|$)',
            self.text, re.DOTALL
        )
        if ref_section:
            block = ref_section.group(1)
            items = re.findall(r'^\s*\d+\.\s*(.+)$', block, re.MULTILINE)
            for item in items[:20]:
                item = item.strip()
                if item and len(item) > 5:
                    refs.append({"type": "book_or_url", "title": item[:200]})
        return refs


class RMdSyllabusParser(MDSyllabusParser):
    """R Markdown 格式 Syllabus 解析器

    在 MD 解析基础上增加：
    - YAML front-matter 提取（title, subtitle, date 等）
    - R 代码块剥离（不干扰表格/标题解析）
    - 行内 R 代码清理
    - 数学公式块保留标记
    """

    _YAML_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    _R_CHUNK_RE = re.compile(r'```{[rR]\s*[^}]*}\n.*?```', re.DOTALL)
    _INLINE_R_RE = re.compile(r'`r\s+[^`]+`')
    _MATH_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)

    def _read(self):
        raw = super()._read()
        self._raw_text = raw
        self._yaml_meta = self._extract_yaml_meta(raw)
        cleaned = self._strip_r_chunks(raw)
        return cleaned

    def _extract_yaml_meta(self, text):
        m = self._YAML_RE.search(text)
        if not m:
            return {}
        yaml_text = m.group(1)
        meta = {}
        for line in yaml_text.split('\n'):
            m2 = re.match(r'^(\w[\w_-]*)\s*:\s*["\']?(.*?)["\']?\s*$', line)
            if m2:
                key = m2.group(1).strip()
                val = m2.group(2).strip().strip('"').strip("'")
                meta[key] = val
        return meta

    def _strip_r_chunks(self, text):
        text = self._YAML_RE.sub('', text, count=1)
        text = self._R_CHUNK_RE.sub('', text)
        text = self._INLINE_R_RE.sub('', text)
        return text

    def _extract_title(self):
        if 'title' in self._yaml_meta:
            t = self._yaml_meta['title']
            if 'subtitle' in self._yaml_meta:
                sub = self._yaml_meta['subtitle']
                if sub and sub not in t:
                    t = f"{t} — {sub}"
            t = re.sub(r'[《》]', '', t).strip()
            t = re.sub(r'[（(]\s*共?\s*\d+\s*课时[）)]', '', t).strip()
            t = re.sub(r'[（(]\s*总?\s*\d+\s*课时.*?[）)]', '', t).strip()
            return t
        return super()._extract_title()

    def parse(self):
        course = super().parse()
        course["source_type"] = "rmd"
        if self._yaml_meta:
            course["yaml_meta"] = self._yaml_meta
        math_blocks = self._MATH_BLOCK_RE.findall(self._raw_text)
        if math_blocks:
            course["math_formulas"] = [f.strip() for f in math_blocks if f.strip()]
        return course


def parse_file(filepath):
    """统一解析入口：自动检测 MD/Rmd 格式"""
    fp = Path(filepath)
    ext = fp.suffix.lower()
    try:
        if ext == '.rmd':
            parser = RMdSyllabusParser(filepath)
        else:
            parser = MDSyllabusParser(filepath)
        return parser.parse()
    except Exception as e:
        print(f"  [WARN] 解析失败 {filepath}: {e}", file=sys.stderr)
        return None


# ─── 批量处理 ─────────────────────────────────────────────────────────

def parse_md_file(filepath):
    """解析单个 MD/Rmd 文件，返回 TS2 格式课程 dict 或 None"""
    return parse_file(filepath)


def parse_md_directory(dirpath, recursive=True):
    """批量解析目录下所有 MD/Rmd Syllabus 文件

    Args:
        dirpath: 目录路径
        recursive: 是否递归扫描子目录，默认 True
    """
    dirpath = Path(dirpath)
    courses = []
    
    if recursive:
        # 递归扫描所有子目录
        md_files = sorted(dirpath.rglob("*.md")) + sorted(dirpath.rglob("*.Rmd")) + sorted(dirpath.rglob("*.rmd"))
    else:
        # 只扫描当前目录
        md_files = sorted(dirpath.glob("*.md")) + sorted(dirpath.glob("*.Rmd")) + sorted(dirpath.glob("*.rmd"))
    
    seen = set()
    for f in md_files:
        if f.name in seen:
            continue
        seen.add(f.name)
        name = f.stem
        if 'Syllabus' not in name and 'syllabus' not in name.lower():
            continue
        course = parse_md_file(f)
        if course and course.get('lessons'):
            courses.append(course)
            print(f"  [OK] {course['course_title']} "
                  f"({course.get('total_hours', '?')}τ, "
                  f"{len(course['lessons'])}条目, "
                  f"域:{course.get('domain', '?')})")
        elif course:
            print(f"  [SKIP] {course['course_title']} (无课时条目)")
    return courses


def build_course_json(courses, output_path=None):
    """构建符合 TS2 格式的 JSON"""
    data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "source": "md_syllabus_parser",
            "framework": "课程处理方程：符号化建模、最佳实践与全日程时刻表",
        },
        "courses": courses,
    }
    if output_path:
        Path(output_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    return data


# ─── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Markdown Syllabus 解析器 (TS2)")
    ap.add_argument("path", help="MD 文件或目录路径")
    ap.add_argument("--output", "-o", help="输出 JSON 路径")
    ap.add_argument("--no-recursive", action="store_true", help="不递归扫描子目录")
    args = ap.parse_args()

    path = Path(args.path)
    courses = []
    if path.is_file():
        course = parse_md_file(path)
        if course:
            courses = [course]
            print(f"✅ 解析完成：{course['course_title']} "
                  f"({course.get('total_hours', '?')}τ, "
                  f"{len(course['lessons'])}条目)")
        else:
            print("❌ 解析失败"); sys.exit(1)
    elif path.is_dir():
        print(f"📂 扫描目录: {path}")
        courses = parse_md_directory(path, recursive=not args.no_recursive)
        print(f"\n✅ 共解析 {len(courses)} 门课程")
    else:
        print(f"❌ 路径不存在: {path}"); sys.exit(1)

    if args.output and courses:
        build_course_json(courses, args.output)
        print(f"📝 已保存到: {args.output}")


# ─── 增强：文档内容提取器 ──────────────────────────────────────────────

@dataclass
class ContentElement:
    """Markdown 内容元素"""
    type: str  # heading, paragraph, formula, code, table, image, link, list, definition, theorem, proof, lemma, example, exercise, remark
    content: str
    level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    line_start: int = 0
    line_end: int = 0

    def to_dict(self) -> Dict:
        return {
            "type": self.type, "content": self.content, "level": self.level,
            "metadata": self.metadata, "line_range": [self.line_start, self.line_end]
        }


@dataclass
class CrossReference:
    """交叉引用"""
    source_line: int
    target_id: str
    target_type: str  # heading, figure, table, equation
    reference_text: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DocumentStats:
    """文档统计"""
    word_count: int = 0
    char_count: int = 0
    line_count: int = 0
    heading_count: int = 0
    formula_count: int = 0
    code_block_count: int = 0
    table_count: int = 0
    image_count: int = 0
    link_count: int = 0
    citation_count: int = 0
    list_count: int = 0
    element_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class QualityIssue:
    """质量问题"""
    type: str
    line: int
    message: str
    severity: str = "warning"  # info, warning, error

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class QualityReport:
    """质量报告"""
    score: float = 100.0
    issues: List[Dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    compatibility: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


# ─── 文档内容提取器 ────────────────────────────────────────────────────

class MarkdownContentExtractor:
    """
    增强 Markdown 内容提取器
    
    从 Markdown 文档中提取结构化内容元素：
    - 标题层级
    - 数学公式（行内和块级）
    - 代码块（带语言标记）
    - 表格
    - 图片/链接
    - Pandoc 扩展环境（definition, theorem, proof 等）
    - 列表
    - 引用块
    """

    # Pandoc 扩展环境
    FENCED_DIV_RE = re.compile(
        r'^:::\s*(\w+)\s*(.*?)$\n(.*?)^:::',
        re.MULTILINE | re.DOTALL
    )

    FORMULA_BLOCK_RE = re.compile(
        r'\$\$(.*?)\$\$',
        re.DOTALL
    )
    FORMULA_INLINE_RE = re.compile(
        r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'
    )
    CODE_BLOCK_RE = re.compile(
        r'```(\w*)\n(.*?)```',
        re.DOTALL
    )
    TABLE_RE = re.compile(
        r'(?:^\|.+\|\n)+(?:^\|[-–—:| ]+\|\n)+(?:^\|.+\|\n)*',
        re.MULTILINE
    )
    IMAGE_RE = re.compile(
        r'!\[([^\]]*)\]\(([^)]+)\)'
    )
    LINK_RE = re.compile(
        r'\[([^\]]+)\]\(([^)]+)\)'
    )
    HEADING_RE = re.compile(
        r'^(#{1,6})\s+(.+?)$',
        re.MULTILINE
    )
    CITATION_RE = re.compile(
        r'[@][\w:.-]+(?:[\s,;]*[@][\w:.-]+)*'
    )
    LIST_RE = re.compile(
        r'^[\s]*[-*+]\s+',
        re.MULTILINE
    )

    PANDOC_ENVS = {'definition', 'theorem', 'proof', 'lemma', 'corollary', 'example', 'exercise', 'remark', 'proposition', 'axiom'}

    def __init__(self, text: str, filepath: str = ""):
        self.text = text
        self.filepath = filepath
        self.lines = text.split('\n')
        self.elements: List[ContentElement] = []
        self.cross_refs: List[CrossReference] = []
        self.stats = DocumentStats()

    def extract_all(self) -> Dict:
        """提取所有结构化内容"""
        self._extract_headings()
        self._extract_formulas()
        self._extract_code_blocks()
        self._extract_tables()
        self._extract_images()
        self._extract_links()
        self._extract_lists()
        self._extract_pandoc_envs()
        self._extract_blockquotes()
        self._extract_citations()
        self._extract_cross_refs()
        self._compute_stats()
        return {
            "elements": [e.to_dict() for e in self.elements],
            "cross_refs": [r.to_dict() for r in self.cross_refs],
            "stats": self.stats.to_dict(),
        }

    def _extract_headings(self):
        for m in self.HEADING_RE.finditer(self.text):
            level = len(m.group(1))
            title = m.group(2).strip()
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="heading", content=title, level=level,
                line_start=line_num, line_end=line_num,
                metadata={"anchor": self._make_anchor(title)}
            ))
            self.stats.heading_count += 1

    def _extract_formulas(self):
        for m in self.FORMULA_BLOCK_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="formula", content=m.group(1).strip(), level=0,
                line_start=line_num,
                metadata={"inline": False}
            ))
            self.stats.formula_count += 1

    def _extract_code_blocks(self):
        for m in self.CODE_BLOCK_RE.finditer(self.text):
            lang = m.group(1) or "unknown"
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="code_block", content=m.group(2).strip(),
                line_start=line_num,
                metadata={"language": lang}
            ))
            self.stats.code_block_count += 1

    def _extract_tables(self):
        for m in self.TABLE_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="table", content=m.group(0).strip(),
                line_start=line_num,
                metadata={"raw": m.group(0)}
            ))
            self.stats.table_count += 1

    def _extract_images(self):
        for m in self.IMAGE_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="image", content="",
                line_start=line_num,
                metadata={"alt": m.group(1), "url": m.group(2)}
            ))
            self.stats.image_count += 1

    def _extract_links(self):
        for m in self.LINK_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="link", content=m.group(1),
                line_start=line_num,
                metadata={"url": m.group(2)}
            ))
            self.stats.link_count += 1

    def _extract_lists(self):
        list_items = []
        for m in self.LIST_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            list_items.append({"line": line_num, "content": m.group(0).strip()})
        if list_items:
            self.elements.append(ContentElement(
                type="list", content=json.dumps(list_items, ensure_ascii=False),
                line_start=list_items[0]["line"],
                metadata={"items": len(list_items)}
            ))
            self.stats.list_count += 1

    def _extract_pandoc_envs(self):
        for m in self.FENCED_DIV_RE.finditer(self.text):
            env_type = m.group(1).lower()
            attrs = m.group(2).strip()
            content = m.group(3).strip()
            line_num = self.text[:m.start()].count('\n') + 1
            if env_type in self.PANDOC_ENVS:
                self.elements.append(ContentElement(
                    type=env_type, content=content,
                    line_start=line_num,
                    metadata={"attributes": attrs}
                ))

    def _extract_blockquotes(self):
        for m in re.finditer(r'^>\s+(.+?)$', self.text, re.MULTILINE):
            line_num = self.text[:m.start()].count('\n') + 1
            self.elements.append(ContentElement(
                type="blockquote", content=m.group(1).strip(),
                line_start=line_num
            ))

    def _extract_citations(self):
        for m in self.CITATION_RE.finditer(self.text):
            line_num = self.text[:m.start()].count('\n') + 1
            citations = [c.strip() for c in m.group(0).split(',') if c.strip()]
            for cite in citations:
                self.elements.append(ContentElement(
                    type="citation", content=cite,
                    line_start=line_num
                ))
                self.stats.citation_count += 1

    def _extract_cross_refs(self):
        # 提取 \@ref(label), @label, [label], eq. (label) 等引用
        ref_patterns = [
            (r'\\@ref\((\w+)\)', 'unknown'),
            (r'@\b(\w[\w-]*)', 'unknown'),
            (r'eq\.\s*\((\w+)\)', 'equation'),
            (r'Fig\.\s*\d+', 'figure'),
            (r'Tab\.\s*\d+', 'table'),
        ]
        for pat, ttype in ref_patterns:
            for m in re.finditer(pat, self.text):
                line_num = self.text[:m.start()].count('\n') + 1
                self.cross_refs.append(CrossReference(
                    source_line=line_num,
                    target_id=m.group(1) if m.lastindex else "",
                    target_type=ttype,
                    reference_text=m.group(0)
                ))

    def _compute_stats(self):
        self.stats.char_count = len(self.text)
        self.stats.line_count = len(self.lines)
        self.stats.word_count = len(re.findall(r'[\w\u4e00-\u9fff]+', self.text))
        self.stats.element_counts = {}
        for e in self.elements:
            self.stats.element_counts[e.type] = self.stats.element_counts.get(e.type, 0) + 1

    @staticmethod
    def _make_anchor(text: str) -> str:
        return re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text.lower()).strip().replace(' ', '-')


# ─── 文档质量评估器 ─────────────────────────────────────────────────────

class DocumentQualityChecker:
    """
    Markdown 文档质量检查器
    
    检查项：
    - 目录完整性
    - 标题层级一致性
    - 图片 alt 文本
    - 代码块语言标记
    - 段落长度
    - Pandoc 兼容性
    - 交叉引用完整性
    """

    def check(self, text: str, elements: List[Dict] = None) -> QualityReport:
        report = QualityReport()
        lines = text.split('\n')

        self._check_heading_hierarchy(lines, report)
        self._check_long_paragraphs(lines, report)
        self._check_code_language(text, report)
        self._check_alt_text(text, report)
        self._check_pandoc_compatibility(text, report)
        self._check_citations(text, report)
        
        # 计算总分
        penalty = 0
        for issue in report.issues:
            if issue.get('severity') == 'error':
                penalty += 10
            elif issue.get('severity') == 'warning':
                penalty += 3
            else:
                penalty += 1
        
        report.score = max(0, 100 - penalty)
        
        # 生成建议
        self._generate_suggestions(report)
        
        return report

    def _check_heading_hierarchy(self, lines, report):
        headings = []
        for i, line in enumerate(lines):
            m = re.match(r'^(#{2,6})\s+', line)
            if m:
                level = len(m.group(1))
                headings.append((level, i + 1))
        
        if not headings:
            report.issues.append({
                "type": "missing_heading", "line": 1,
                "message": "文档缺少标题", "severity": "warning"
            })
            return

        # 检查层级跳跃
        for i in range(1, len(headings)):
            prev_level, _ = headings[i - 1]
            curr_level, line = headings[i]
            if curr_level > prev_level + 1:
                report.issues.append({
                    "type": "heading_skip", "line": line,
                    "message": f"标题层级从 H{prev_level} 跳到 H{curr_level}（建议逐级）",
                    "severity": "warning"
                })

    def _check_long_paragraphs(self, lines, report):
        current_para = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('-') and not stripped.startswith('*'):
                current_para.append(stripped)
            else:
                if len(current_para) > 1:
                    full_para = ' '.join(current_para)
                    if len(full_para) > 500:
                        report.issues.append({
                            "type": "long_paragraph", "line": i - len(current_para) + 1,
                            "message": f"段落过长（{len(full_para)} 字符），建议拆分",
                            "severity": "info"
                        })
                current_para = []

    def _check_code_language(self, text, report):
        for m in re.finditer(r'```(\w*)\n', text):
            lang = m.group(1)
            if not lang:
                line = text[:m.start()].count('\n') + 1
                report.issues.append({
                    "type": "no_code_language", "line": line,
                    "message": "代码块缺少语言标记",
                    "severity": "info"
                })

    def _check_alt_text(self, text, report):
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
            alt = m.group(1).strip()
            if not alt:
                line = text[:m.start()].count('\n') + 1
                report.issues.append({
                    "type": "missing_alt_text", "line": line,
                    "message": "图片缺少 alt 文本",
                    "severity": "warning"
                })

    def _check_pandoc_compatibility(self, text, report):
        # 检查是否使用了 Pandoc 不支持的语法
        compatibility = {
            "pandoc": True,
            "bookdown": True,
            "github_flavored": True,
        }
        
        # 检查 bookdown 特有语法
        has_bookdown_refs = bool(re.search(r'\\@ref\(|\{@\w+[-\w]*\}', text))
        compatibility["bookdown"] = has_bookdown_refs
        
        # 检查 pandoc 兼容性
        has_unsupported_html = bool(re.search(r'<(?!br/?\s*/?|em|strong|i|b|code|span|div|p|ul|ol|li|table|thead|tbody|tr|td|th|hr|h[1-6]|a\s|img\s)[a-zA-Z][^>]*>', text))
        compatibility["pandoc"] = not has_unsupported_html
        
        report.compatibility = compatibility

    def _check_citations(self, text, report):
        # 检查是否有 [@cite] 格式
        if '@' in text:
            citations = re.findall(r'[@][\w:.-]+', text)
            if not citations and re.search(r'参考文献', text):
                report.issues.append({
                    "type": "missing_citation", "line": 1,
                    "message": "文档有参考文献部分但未使用 Pandoc 引用语法",
                    "severity": "info"
                })

    def _generate_suggestions(self, report):
        issue_types = {i['type'] for i in report.issues}
        
        if "missing_heading" in issue_types:
            report.suggestions.append("建议添加一级标题作为文档标题")
        if "heading_skip" in issue_types:
            report.suggestions.append("建议标题层级逐级递增，不要跳跃")
        if "long_paragraph" in issue_types:
            report.suggestions.append("长段落建议拆分为多个短段落，提高可读性")
        if "no_code_language" in issue_types:
            report.suggestions.append("为代码块添加语言标记（如 ```python）以启用语法高亮")
        if "missing_alt_text" in issue_types:
            report.suggestions.append("为图片添加描述性 alt 文本，提升可访问性")


# ─── 智能文档分类器 ─────────────────────────────────────────────────────

class DocumentClassifier:
    """
    智能文档分类器
    
    根据内容特征自动分类文档类型
    """
    
    CLASS_PATTERNS = {
        "course_note": {
            "keywords": ["课时", "课程", "Syllabus", "学习进度", "第.*节", "第.*章", "Section"],
            "min_matches": 2
        },
        "theorem_proof": {
            "keywords": ["定理", "证明", "引理", "推论", "命题", "定义", "公理", "Theorem", "Proof", "Lemma", "Definition"],
            "min_matches": 3
        },
        "code_example": {
            "keywords": ["```", "import ", "def ", "class ", "function", "代码", "实现"],
            "min_matches": 3
        },
        "homework": {
            "keywords": ["作业", "习题", "练习", "解答", "答案", "解答过程", "Homework", "Exercise", "Problem"],
            "min_matches": 2
        },
        "lab_report": {
            "keywords": ["实验", "数据", "结果", "分析", "结论", "方法", "材料", "Experiment", "Lab"],
            "min_matches": 2
        },
        "textbook": {
            "keywords": ["教材", "课本", "第.*版", "出版社", "ISBN", "作者", "主编"],
            "min_matches": 2
        },
        "research_paper": {
            "keywords": ["摘要", "关键词", "引言", "相关工作", "实验结果", "结论", "Abstract", "Introduction"],
            "min_matches": 3
        },
    }

    @classmethod
    def classify(cls, text: str, content_elements: List[Dict] = None) -> Tuple[str, float, Dict]:
        """
        分类文档，返回 (category, confidence, details)
        """
        text_lower = text.lower()
        scores = {}
        details = {}

        for category, config in cls.CLASS_PATTERNS.items():
            matches = 0
            matched_kws = []
            for kw in config["keywords"]:
                if re.search(kw, text_lower if kw.islower() else text):
                    matches += 1
                    matched_kws.append(kw)
            scores[category] = matches
            details[category] = {"matches": matches, "keywords": matched_kws}

        best_category = "general"
        best_score = 0
        
        for cat, score in scores.items():
            if score >= cls.CLASS_PATTERNS[cat]["min_matches"] and score > best_score:
                best_category = cat
                best_score = score

        max_possible = max(len(config["keywords"]) for config in cls.CLASS_PATTERNS.values())
        confidence = min(1.0, best_score / max_possible) if max_possible > 0 else 0.0

        return best_category, confidence, details


# ─── 课程资源扫描与分配 ─────────────────────────────────────────────────

class CourseResourceScanner:
    """
    课程资源扫描与分配器
    
    功能：
    1. 扫描目录中的所有学习资源文件
    2. 智能分类（讲义、习题、代码、视频链接、参考文献等）
    3. 自动匹配到对应课程
    4. 生成导入建议
    """

    # 文件类型到资源类型的映射
    FILE_TYPE_MAP = {
        # 文档类
        ".pdf": "document",
        ".doc": "document",
        ".docx": "document",
        ".md": "markdown",
        ".rmd": "rmarkdown",
        ".tex": "latex",
        ".txt": "text",
        # 代码类
        ".py": "code",
        ".r": "code",
        ".R": "code",
        ".jl": "code",
        ".m": "code",
        ".ipynb": "notebook",
        ".cpp": "code",
        ".c": "code",
        ".java": "code",
        # 数据类
        ".csv": "data",
        ".json": "data",
        ".xlsx": "data",
        ".xls": "data",
        ".tsv": "data",
        ".mat": "data",
        ".h5": "data",
        ".hdf5": "data",
        # 图片类
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".svg": "image",
        # 演示类
        ".ppt": "presentation",
        ".pptx": "presentation",
        ".key": "presentation",
        # 视频类
        ".mp4": "video",
        ".avi": "video",
        ".mov": "video",
        # 音频类
        ".mp3": "audio",
        ".wav": "audio",
        ".flac": "audio",
    }

    # 文件名模式到课时分配的启发式规则
    LESSON_PATTERNS = [
        (re.compile(r'[Ll]esson[_\-]*(\d+)', re.IGNORECASE), "lesson_number"),
        (re.compile(r'[Ll]ec[_\-]*(\d+)', re.IGNORECASE), "lesson_number"),
        (re.compile(r'[Cc]hapter[_\-]*(\d+)', re.IGNORECASE), "chapter"),
        (re.compile(r'[Cc]h[_\-]*(\d+)', re.IGNORECASE), "chapter"),
        (re.compile(r'[Ss]ec[_\-]*(\d+)', re.IGNORECASE), "section"),
        (re.compile(r'[Ss]ection[_\-]*(\d+)', re.IGNORECASE), "section"),
        (re.compile(r'^(\d+)[_\s]', re.IGNORECASE), "number_prefix"),
        (re.compile(r'[（(](\d+)[）)]', re.IGNORECASE), "parenthesized_number"),
    ]

    def __init__(self, base_dir: str = ""):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.resources: List[Dict] = []
        self.course_mapping: Dict[str, List[Dict]] = {}

    def scan_directory(self, dirpath: str = None, recursive: bool = True) -> List[Dict]:
        """扫描目录，提取所有学习资源"""
        scan_dir = Path(dirpath) if dirpath else self.base_dir
        self.resources = []

        # 扩展名过滤
        valid_exts = set(self.FILE_TYPE_MAP.keys())
        
        if recursive:
            files = sorted([f for f in scan_dir.rglob('*') if f.is_file() and f.suffix.lower() in valid_exts])
        else:
            files = sorted([f for f in scan_dir.glob('*') if f.is_file() and f.suffix.lower() in valid_exts])

        for f in files:
            try:
                rel_path = f.relative_to(scan_dir)
                resource = self._analyze_file(f, rel_path)
                self.resources.append(resource)
            except Exception as e:
                print(f"  [WARN] 分析文件失败 {f}: {e}")

        return self.resources

    def _analyze_file(self, filepath: Path, rel_path: Path) -> Dict:
        """分析单个文件，提取元数据"""
        ext = filepath.suffix.lower()
        name = filepath.stem
        
        # 基本属性
        resource = {
            "filepath": str(filepath),
            "relative_path": str(rel_path),
            "filename": filepath.name,
            "stem": name,
            "extension": ext,
            "resource_type": self.FILE_TYPE_MAP.get(ext, "other"),
            "size_bytes": filepath.stat().st_size if filepath.exists() else 0,
            "matched_courses": [],
            "matched_lessons": [],
            "extracted_metadata": {},
        }

        # 提取课时编号
        lesson_info = self._extract_lesson_info(name)
        if lesson_info:
            resource["extracted_metadata"]["lesson"] = lesson_info

        # 提取主题关键词
        keywords = self._extract_keywords(name)
        if keywords:
            resource["extracted_metadata"]["keywords"] = keywords

        # 智能分类标签
        tags = self._generate_tags(name, ext)
        resource["tags"] = tags

        return resource

    def _extract_lesson_info(self, name: str) -> Optional[Dict]:
        """从文件名提取课时/章节信息"""
        for pattern, info_type in self.LESSON_PATTERNS:
            m = pattern.search(name)
            if m:
                return {"type": info_type, "number": int(m.group(1))}
        return None

    # ═══════════════════════════════════════════════════════════
    # 领域词汇映射（中英文双向）+ 停用词表
    # ═══════════════════════════════════════════════════════════
    
    DOMAIN_KEYWORDS_FULL = {
        # 代数领域
        'algebra': ['代数', '线性代数', '抽象代数', '高等代数'],
        'linear': ['线性', '线性代数'],
        'group': ['群', '群论'],
        'ring': ['环', '环论'],
        'field': ['域', '域论'],
        'module': ['模', '模论'],
        'galois': ['伽罗瓦', '伽罗瓦理论'],
        'representation': ['表示', '表示论'],
        'lie': ['李', '李代数', '李群'],
        'abelian': ['阿贝尔', '阿贝尔群'],
        'commutative': ['交换', '交换代数'],
        'tensor': ['张量', '张量代数'],
        'matrix': ['矩阵'],
        'vector': ['向量'],
        'polynomial': ['多项式'],
        'ideal': ['理想'],
        'boolean': ['布尔', '布尔代数'],
        # 几何领域
        'geometry': ['几何', '几何学', '解析几何'],
        'differential': ['微分', '微分几何'],
        'riemann': ['黎曼', '黎曼几何'],
        'manifold': ['流形'],
        'curvature': ['曲率'],
        'topology': ['拓扑', '拓扑学'],
        'homotopy': ['同伦', '同伦论'],
        'homology': ['同调', '同调论'],
        'cohomology': ['上同调', '上同调论'],
        'sheaf': ['层', '层论'],
        'scheme': ['概形'],
        'algebraic': ['代数几何'],
        'projective': ['射影', '射影几何'],
        'affine': ['仿射', '仿射几何'],
        'complex': ['复几何', '复分析'],
        'symplectic': ['辛几何'],
        # 分析领域
        'analysis': ['分析', '数学分析'],
        'calculus': ['微积分'],
        'functional': ['泛函', '泛函分析'],
        'measure': ['测度', '测度论'],
        'fourier': ['傅里叶'],
        'operator': ['算子', '算子理论'],
        'spectral': ['谱', '谱理论'],
        'pde': ['偏微分方程'],
        'ode': ['常微分方程'],
        'integral': ['积分', '积分方程'],
        'variational': ['变分', '变分法'],
        'distribution': ['分布', '广义函数'],
        # 物理领域
        'physics': ['物理', '物理学'],
        'mechanics': ['力学'],
        'quantum': ['量子', '量子力学'],
        'electrodynamics': ['电动力学'],
        'thermodynamics': ['热力学'],
        'relativity': ['相对论'],
        'statistical': ['统计物理', '统计力学'],
        'particle': ['粒子物理'],
        'classical': ['经典力学'],
        'newtonian': ['牛顿力学'],
        'lagrangian': ['拉格朗日'],
        'hamiltonian': ['哈密顿'],
        'optics': ['光学'],
        'electromagnetism': ['电磁学'],
        'cosmology': ['宇宙学'],
        'astrophysics': ['天体物理'],
        'string': ['弦论'],
        'condensed': ['凝聚态'],
        'solid': ['固体物理'],
        # 计算机领域
        'algorithm': ['算法'],
        'programming': ['编程', '程序设计'],
        'data': ['数据'],
        'structure': ['结构'],
        'machine': ['机器学习'],
        'learning': ['学习'],
        'neural': ['神经网络'],
        'deep': ['深度学习'],
        'artificial': ['人工智能'],
        'intelligence': ['智能'],
        'database': ['数据库'],
        'network': ['网络'],
        'security': ['安全', '网络安全'],
        'cryptography': ['密码学'],
        'graphics': ['图形学'],
        'vision': ['视觉', '计算机视觉'],
        'operating': ['操作系统'],
        'compiler': ['编译原理'],
        'software': ['软件工程'],
        # 数学通用
        'number': ['数论', '数字'],
        'theory': ['理论'],
        'combinatorics': ['组合数学'],
        'graph': ['图论'],
        'optimization': ['最优化', '优化'],
        'probability': ['概率', '概率论'],
        'statistics': ['统计', '统计学'],
        'stochastic': ['随机', '随机过程'],
        'numerical': ['数值分析', '数值计算'],
        'transform': ['变换'],
        'laplace': ['拉普拉斯'],
        'equation': ['方程'],
        'theorem': ['定理'],
        'proof': ['证明'],
        'axiom': ['公理'],
        'limit': ['极限'],
        'derivative': ['导数'],
        'gradient': ['梯度'],
        'eigenvalue': ['特征值'],
        'eigenvector': ['特征向量'],
        'determinant': ['行列式'],
        'convergence': ['收敛'],
        'divergence': ['发散'],
        'sequence': ['数列'],
        'series': ['级数'],
        # 英文学术通用词 → 领域映射
        'mathematical': ['数学'],
        'discrete': ['离散', '离散数学'],
        'continuous': ['连续'],
        'abstract': ['抽象'],
        'applied': ['应用'],
        'pure': ['纯粹', '纯数学'],
        'elementary': ['初等'],
        'advanced': ['高等', '进阶'],
        'intermediate': ['中级'],
        'fundamental': ['基础', '基本原理'],
        'fundamentals': ['基础', '基本原理'],
        'introduction': ['导论', '入门', '引论'],
        'introductory': ['导论', '入门'],
        'modern': ['现代'],
        'classical': ['经典'],
        'general': ['一般', '概论'],
        'special': ['特殊', '专题'],
        'methods': ['方法'],
        'method': ['方法'],
        'approach': ['方法', '途径'],
        'techniques': ['技术', '技巧'],
        'structures': ['结构'],
        'structural': ['结构'],
        'geometric': ['几何'],
        'algebraic': ['代数'],
        'analytic': ['分析', '解析'],
        'analytical': ['分析', '解析'],
        'topological': ['拓扑'],
        'differential': ['微分'],
        'integral': ['积分'],
        'functional': ['泛函'],
        'computational': ['计算'],
        'algorithmic': ['算法'],
        'statistical': ['统计'],
        'physical': ['物理'],
        'theoretical': ['理论'],
        'experimental': ['实验'],
        'practical': ['实践'],
        'systematic': ['系统'],
        'comprehensive': ['综合'],
        'essential': ['基础', '核心'],
        'essentials': ['基础', '核心'],
        'principles': ['原理'],
        'principle': ['原理'],
        'concepts': ['概念'],
        'concept': ['概念'],
        'foundations': ['基础'],
        'foundation': ['基础'],
        'basics': ['基础'],
        'basic': ['基础'],
        'textbook': ['教材'],
        'reference': ['参考'],
        'handbook': ['手册'],
        'dictionary': ['词典'],
        'encyclopedia': ['百科'],
        'companion': ['指南'],
        'guide': ['指南'],
        'manual': ['手册'],
        'compendium': ['概要'],
        'treatise': ['论著'],
        'monograph': ['专著'],
        'spirit': ['精神'],
        'beautiful': ['优美', '美丽'],
        'elegant': ['优雅'],
        'powerful': ['强大', '有力'],
        'deep': ['深刻', '深度'],
        'rigorous': ['严谨'],
        'complete': ['完整', '完全'],
        'full': ['完整', '全部'],
        'concise': ['简明'],
        'clear': ['清晰', '清楚'],
        'intuitive': ['直观'],
        'visual': ['可视化', '直观'],
        'computing': ['计算'],
        'computer': ['计算机'],
        'information': ['信息'],
        'science': ['科学'],
        'engineering': ['工程'],
        'technology': ['技术'],
        'design': ['设计'],
        'architecture': ['架构'],
        'implementation': ['实现'],
        'practice': ['实践'],
        'experience': ['经验'],
        'perspective': ['视角', '观点'],
        'overview': ['概述'],
        'survey': ['综述'],
        'review': ['复习', '综述'],
        'study': ['研究', '学习'],
        'exploration': ['探索'],
        'investigation': ['调查', '研究'],
        'discovery': ['发现'],
        'innovation': ['创新'],
        'evolution': ['演变', '进化'],
        'development': ['发展'],
        'progress': ['进展'],
        'advances': ['进展', '进步'],
        'frontiers': ['前沿'],
        'frontier': ['前沿'],
        'horizons': ['视野'],
        'vistas': ['远景'],
        'landscapes': ['全景'],
        'paradigm': ['范式'],
        'framework': ['框架'],
        'model': ['模型'],
        'models': ['模型'],
        'theory': ['理论'],
        'theories': ['理论'],
        'hypothesis': ['假设'],
        'conjecture': ['猜想'],
        'observation': ['观察'],
        'phenomenon': ['现象'],
        'properties': ['性质'],
        'property': ['性质', '属性'],
        'behavior': ['行为'],
        'dynamics': ['动态', '动力学'],
        'processes': ['过程'],
        'process': ['过程'],
        'systems': ['系统'],
        'networks': ['网络'],
        'patterns': ['模式'],
        'pattern': ['模式'],
        'relations': ['关系'],
        'relation': ['关系'],
        'functions': ['函数'],
        'function': ['函数'],
        'variables': ['变量'],
        'variable': ['变量'],
        'parameters': ['参数'],
        'parameter': ['参数'],
        'dimensions': ['维度'],
        'dimension': ['维度'],
        'spaces': ['空间'],
        'space': ['空间'],
        'fields': ['领域', '场'],
        'field': ['领域', '场'],
        'groups': ['群'],
        'group': ['群'],
        'rings': ['环'],
        'ring': ['环'],
        'modules': ['模'],
        'module': ['模'],
        'ideals': ['理想'],
        'ideal': ['理想'],
        'categories': ['范畴'],
        'category': ['范畴'],
        'functors': ['函子'],
        'functor': ['函子'],
        'morphisms': ['态射'],
        'morphism': ['态射'],
        'homomorphisms': ['同态'],
        'homomorphism': ['同态'],
        'isomorphisms': ['同构'],
        'isomorphism': ['同构'],
        'automorphisms': ['自同构'],
        'automorphism': ['自同构'],
        'endomorphisms': ['自同态'],
        'endomorphism': ['自同态'],
        'curves': ['曲线'],
        'curve': ['曲线'],
        'surfaces': ['曲面'],
        'surface': ['曲面'],
        'manifolds': ['流形'],
        'manifold': ['流形'],
        'bundles': ['丛'],
        'bundle': ['丛'],
        'sheaves': ['层'],
        'sheaf': ['层'],
        'spectra': ['谱'],
        'spectrum': ['谱'],
        'residues': ['留数'],
        'residue': ['留数'],
        'singularities': ['奇点'],
        'singularity': ['奇点'],
        'symmetries': ['对称'],
        'symmetry': ['对称'],
        'invariants': ['不变量'],
        'invariant': ['不变量'],
        'operators': ['算子'],
        'operator': ['算子'],
        'algebras': ['代数'],
        'algebra': ['代数'],
        'polynomials': ['多项式'],
        'polynomial': ['多项式'],
        'matrices': ['矩阵'],
        'matrix': ['矩阵'],
        'vectors': ['向量'],
        'vector': ['向量'],
        'tensors': ['张量'],
        'tensor': ['张量'],
        'forms': ['形式'],
        'form': ['形式'],
        'equations': ['方程'],
        'equation': ['方程'],
        'inequalities': ['不等式'],
        'inequality': ['不等式'],
        'estimates': ['估计'],
        'estimate': ['估计'],
        'bounds': ['界'],
        'bound': ['界'],
        'approximations': ['近似'],
        'approximation': ['近似'],
        'errors': ['误差'],
        'error': ['误差'],
        'solutions': ['解'],
        'solution': ['解'],
        'algorithms': ['算法'],
        'algorithm': ['算法'],
        'procedures': ['过程'],
        'procedure': ['过程'],
        'programs': ['程序'],
        'program': ['程序'],
        'codes': ['代码'],
        'code': ['代码'],
        'languages': ['语言'],
        'language': ['语言'],
        'compilers': ['编译器'],
        'compiler': ['编译器'],
        'interpreters': ['解释器'],
        'interpreter': ['解释器'],
        'parsers': ['解析器'],
        'parser': ['解析器'],
        'lexers': ['词法分析器'],
        'lexer': ['词法分析器'],
        'grammars': ['语法'],
        'grammar': ['语法'],
        'automata': ['自动机'],
        'automaton': ['自动机'],
        'machines': ['机器'],
        'machine': ['机器'],
        'complexity': ['复杂度'],
        'hardness': ['难度'],
        'tractability': ['可解性'],
        'computability': ['可计算性'],
        'decidability': ['可判定性'],
        'completeness': ['完备性'],
        'soundness': ['可靠性'],
        'consistency': ['一致性'],
        'correctness': ['正确性'],
        'efficiency': ['效率'],
        'performance': ['性能'],
        'optimality': ['最优性'],
        'robustness': ['鲁棒性'],
        'scalability': ['可扩展性'],
        'reliability': ['可靠性'],
        'maintainability': ['可维护性'],
        'readability': ['可读性'],
        'usability': ['可用性'],
        'portability': ['可移植性'],
        'compatibility': ['兼容性'],
        'interoperability': ['互操作性'],
        'security': ['安全'],
        'privacy': ['隐私'],
        'authentication': ['认证'],
        'authorization': ['授权'],
        'encryption': ['加密'],
        'decryption': ['解密'],
        'hashing': ['哈希'],
        'signatures': ['签名'],
        'signature': ['签名'],
        'protocols': ['协议'],
        'protocol': ['协议'],
        'standards': ['标准'],
        'standard': ['标准'],
        'specifications': ['规范'],
        'specification': ['规范'],
        'requirements': ['需求'],
        'requirement': ['需求'],
        'constraints': ['约束'],
        'constraint': ['约束'],
        'limitations': ['限制'],
        'limitation': ['限制'],
        'assumptions': ['假设'],
        'assumption': ['假设'],
        'conditions': ['条件'],
        'condition': ['条件'],
        'criteria': ['标准'],
        'criterion': ['标准'],
        'metrics': ['指标'],
        'metric': ['指标'],
        'measurements': ['测量'],
        'measurement': ['测量'],
        'evaluations': ['评估'],
        'evaluation': ['评估'],
        'assessments': ['评估'],
        'assessment': ['评估'],
        'analyses': ['分析'],
        'analysis': ['分析'],
        'examinations': ['检查'],
        'examination': ['检查'],
        'investigations': ['调查'],
        'investigation': ['调查'],
        'explorations': ['探索'],
        'exploration': ['探索'],
        'discoveries': ['发现'],
        'discovery': ['发现'],
        'inventions': ['发明'],
        'invention': ['发明'],
        'creations': ['创造'],
        'creation': ['创造'],
        'productions': ['生产'],
        'production': ['生产'],
        'generations': ['生成'],
        'generation': ['生成'],
        'transformations': ['变换'],
        'transformation': ['变换'],
        'translations': ['翻译'],
        'translation': ['翻译'],
        'interpretations': ['解释'],
        'interpretation': ['解释'],
        'representations': ['表示'],
        'representation': ['表示'],
        'presentations': ['展示'],
        'presentation': ['展示'],
        'illustrations': ['说明'],
        'illustration': ['说明'],
        'demonstrations': ['演示'],
        'demonstration': ['演示'],
        'examples': ['示例'],
        'example': ['示例'],
        'cases': ['案例'],
        'case': ['案例'],
        'instances': ['实例'],
        'instance': ['实例'],
        'samples': ['样本'],
        'sample': ['样本'],
        'specimens': ['标本'],
        'specimen': ['标本'],
        'experiments': ['实验'],
        'experiment': ['实验'],
        'trials': ['试验'],
        'trial': ['试验'],
        'tests': ['测试'],
        'test': ['测试'],
        'validations': ['验证'],
        'validation': ['验证'],
        'verifications': ['核实'],
        'verification': ['核实'],
        'confirmations': ['确认'],
        'confirmation': ['确认'],
        'certifications': ['认证'],
        'certification': ['认证'],
        'qualifications': ['资格'],
        'qualification': ['资格'],
        'credentials': ['凭证'],
        'credential': ['凭证'],
        'authorizations': ['授权'],
        'authorization': ['授权'],
        'permissions': ['权限'],
        'permission': ['权限'],
        'privileges': ['特权'],
        'privilege': ['特权'],
        'rights': ['权利'],
        'right': ['权利'],
        'responsibilities': ['责任'],
        'responsibility': ['责任'],
        'duties': ['职责'],
        'duty': ['职责'],
        'obligations': ['义务'],
        'obligation': ['义务'],
        'commitments': ['承诺'],
        'commitment': ['承诺'],
        'agreements': ['协议'],
        'agreement': ['协议'],
        'contracts': ['合同'],
        'contract': ['合同'],
        'treaties': ['条约'],
        'treaty': ['条约'],
        'pacts': ['协定'],
        'pact': ['协定'],
        'alliances': ['联盟'],
        'alliance': ['联盟'],
        'coalitions': ['联盟'],
        'coalition': ['联盟'],
        'partnerships': ['合作伙伴'],
        'partnership': ['合作伙伴'],
        'collaborations': ['协作'],
        'collaboration': ['协作'],
        'cooperations': ['合作'],
        'cooperation': ['合作'],
        'coordinations': ['协调'],
        'coordination': ['协调'],
        'integrations': ['集成'],
        'integration': ['集成'],
        'consolidations': ['合并'],
        'consolidation': ['合并'],
        'unifications': ['统一'],
        'unification': ['统一'],
        'harmonizations': ['协调'],
        'harmonization': ['协调'],
        'synchronizations': ['同步'],
        'synchronization': ['同步'],
        'alignments': ['对齐'],
        'alignment': ['对齐'],
        'adjustments': ['调整'],
        'adjustment': ['调整'],
        'modifications': ['修改'],
        'modification': ['修改'],
        'alterations': ['更改'],
        'alteration': ['更改'],
        'variations': ['变化'],
        'variation': ['变化'],
        'changes': ['变化'],
        'change': ['变化'],
        'shifts': ['转变'],
        'shift': ['转变'],
        'transitions': ['过渡'],
        'transition': ['过渡'],
        'migrations': ['迁移'],
        'migration': ['迁移'],
        'conversions': ['转换'],
        'conversion': ['转换'],
        'adaptations': ['适应'],
        'adaptation': ['适应'],
        'adjustments': ['调整'],
        'adjustment': ['调整'],
        'customizations': ['定制'],
        'customization': ['定制'],
        'configurations': ['配置'],
        'configuration': ['配置'],
        'settings': ['设置'],
        'setting': ['设置'],
        'preferences': ['偏好'],
        'preference': ['偏好'],
        'options': ['选项'],
        'option': ['选项'],
        'choices': ['选择'],
        'choice': ['选择'],
        'decisions': ['决定'],
        'decision': ['决定'],
        'selections': ['选择'],
        'selection': ['选择'],
        'picks': ['挑选'],
        'pick': ['挑选'],
        'votes': ['投票'],
        'vote': ['投票'],
        'elections': ['选举'],
        'election': ['选举'],
        'nominations': ['提名'],
        'nomination': ['提名'],
        'appointments': ['任命'],
        'appointment': ['任命'],
        'assignments': ['分配'],
        'assignment': ['分配'],
        'allocations': ['分配'],
        'allocation': ['分配'],
        'distributions': ['分配'],
        'distribution': ['分配'],
        'deliveries': ['交付'],
        'delivery': ['交付'],
        'shipments': ['发货'],
        'shipment': ['发货'],
        'transports': ['运输'],
        'transport': ['运输'],
        'transfers': ['转移'],
        'transfer': ['转移'],
        'exchanges': ['交换'],
        'exchange': ['交换'],
        'swaps': ['交换'],
        'swap': ['交换'],
        'trades': ['贸易'],
        'trade': ['贸易'],
        'transactions': ['交易'],
        'transaction': ['交易'],
        'deals': ['交易'],
        'deal': ['交易'],
        'bargains': ['议价'],
        'bargain': ['议价'],
        'negotiations': ['谈判'],
        'negotiation': ['谈判'],
        'discussions': ['讨论'],
        'discussion': ['讨论'],
        'conversations': ['对话'],
        'conversation': ['对话'],
        'communications': ['通信'],
        'communication': ['通信'],
        'messages': ['消息'],
        'message': ['消息'],
        'notifications': ['通知'],
        'notification': ['通知'],
        'announcements': ['公告'],
        'announcement': ['公告'],
        'declarations': ['声明'],
        'declaration': ['声明'],
        'proclamations': ['公告'],
        'proclamation': ['公告'],
        'statements': ['声明'],
        'statement': ['声明'],
        'assertions': ['断言'],
        'assertion': ['断言'],
        'claims': ['声明'],
        'claim': ['声明'],
        'arguments': ['论证'],
        'argument': ['论证'],
        'reasons': ['原因'],
        'reason': ['原因'],
        'justifications': ['正当理由'],
        'justification': ['正当理由'],
        'explanations': ['解释'],
        'explanation': ['解释'],
        'clarifications': ['澄清'],
        'clarification': ['澄清'],
        'elucidations': ['阐明'],
        'elucidation': ['阐明'],
        'interpretations': ['解释'],
        'interpretation': ['解释'],
        'translations': ['翻译'],
        'translation': ['翻译'],
        'versions': ['版本'],
        'version': ['版本'],
        'editions': ['版本'],
        'edition': ['版本'],
        'revisions': ['修订'],
        'revision': ['修订'],
        'updates': ['更新'],
        'update': ['更新'],
        'upgrades': ['升级'],
        'upgrade': ['升级'],
        'improvements': ['改进'],
        'improvement': ['改进'],
        'enhancements': ['增强'],
        'enhancement': ['增强'],
        'refinements': ['精炼'],
        'refinement': ['精炼'],
        'optimizations': ['优化'],
        'optimization': ['优化'],
        'fine-tunings': ['微调'],
        'fine-tuning': ['微调'],
        'calibrations': ['校准'],
        'calibration': ['校准'],
        'adjustments': ['调整'],
        'adjustment': ['调整'],
        'tunings': ['调谐'],
        'tuning': ['调谐'],
        'settings': ['设置'],
        'setting': ['设置'],
        'configurations': ['配置'],
        'configuration': ['配置'],
        'arrangements': ['安排'],
        'arrangement': ['安排'],
        'organizations': ['组织'],
        'organization': ['组织'],
        'structures': ['结构'],
        'structure': ['结构'],
        'architectures': ['架构'],
        'architecture': ['架构'],
        'designs': ['设计'],
        'design': ['设计'],
        'plans': ['计划'],
        'plan': ['计划'],
        'blueprints': ['蓝图'],
        'blueprint': ['蓝图'],
        'schemas': ['模式'],
        'schema': ['模式'],
        'templates': ['模板'],
        'template': ['模板'],
        'patterns': ['模式'],
        'pattern': ['模式'],
        'models': ['模型'],
        'model': ['模型'],
        'prototypes': ['原型'],
        'prototype': ['原型'],
        'mockups': ['模拟'],
        'mockup': ['模拟'],
        'drafts': ['草稿'],
        'draft': ['草稿'],
        'sketches': ['草图'],
        'sketch': ['草图'],
        'outlines': ['大纲'],
        'outline': ['大纲'],
        'summaries': ['摘要'],
        'summary': ['摘要'],
        'abstracts': ['摘要'],
        'abstract': ['摘要'],
        'synopses': ['大纲'],
        'synopsis': ['大纲'],
        'overviews': ['概述'],
        'overview': ['概述'],
        'reviews': ['复习'],
        'review': ['复习'],
        'surveys': ['调查'],
        'survey': ['调查'],
        'assessments': ['评估'],
        'assessment': ['评估'],
        'evaluations': ['评估'],
        'evaluation': ['评估'],
        'appraisals': ['评估'],
        'appraisal': ['评估'],
        'estimations': ['估算'],
        'estimation': ['估算'],
        'calculations': ['计算'],
        'calculation': ['计算'],
        'computations': ['计算'],
        'computation': ['计算'],
        'operations': ['操作'],
        'operation': ['操作'],
        'procedures': ['过程'],
        'procedure': ['过程'],
        'processes': ['过程'],
        'process': ['过程'],
        'workflows': ['流程'],
        'workflow': ['流程'],
        'pipelines': ['管道'],
        'pipeline': ['管道'],
        'sequences': ['序列'],
        'sequence': ['序列'],
        'series': ['系列'],
        'series': ['系列'],
        'chains': ['链'],
        'chain': ['链'],
        'links': ['链接'],
        'link': ['链接'],
        'connections': ['连接'],
        'connection': ['连接'],
        'relationships': ['关系'],
        'relationship': ['关系'],
        'associations': ['关联'],
        'association': ['关联'],
        'correlations': ['相关'],
        'correlation': ['相关'],
        'dependencies': ['依赖'],
        'dependency': ['依赖'],
        'requisites': ['必要条件'],
        'requisite': ['必要条件'],
        'requirements': ['需求'],
        'requirement': ['需求'],
        'necessities': ['必需品'],
        'necessity': ['必需品'],
        'essentials': ['必需品'],
        'essential': ['必需品'],
        'basics': ['基础'],
        'basic': ['基础'],
        'fundamentals': ['基础'],
        'fundamental': ['基础'],
        'principles': ['原理'],
        'principle': ['原理'],
        'rules': ['规则'],
        'rule': ['规则'],
        'regulations': ['规章'],
        'regulation': ['规章'],
        'guidelines': ['指南'],
        'guideline': ['指南'],
        'instructions': ['说明'],
        'instruction': ['说明'],
        'directions': ['说明'],
        'direction': ['说明'],
        'commands': ['命令'],
        'command': ['命令'],
        'orders': ['命令'],
        'order': ['命令'],
        'requests': ['请求'],
        'request': ['请求'],
        'queries': ['查询'],
        'query': ['查询'],
        'questions': ['问题'],
        'question': ['问题'],
        'inquiries': ['询问'],
        'inquiry': ['询问'],
        'investigations': ['调查'],
        'investigation': ['调查'],
        'examinations': ['检查'],
        'examination': ['检查'],
        'inspections': ['检查'],
        'inspection': ['检查'],
        'audits': ['审计'],
        'audit': ['审计'],
        'reviews': ['复查'],
        'review': ['复查'],
        'checks': ['检查'],
        'check': ['检查'],
        'verifications': ['验证'],
        'verification': ['验证'],
        'validations': ['验证'],
        'validation': ['验证'],
        'confirmations': ['确认'],
        'confirmation': ['确认'],
        'certifications': ['认证'],
        'certification': ['认证'],
        'qualifications': ['资格'],
        'qualification': ['资格'],
        'accreditations': ['认证'],
        'accreditation': ['认证'],
        'endorsements': ['认可'],
        'endorsement': ['认可'],
        'approvals': ['批准'],
        'approval': ['批准'],
        'permissions': ['许可'],
        'permission': ['许可'],
        'authorizations': ['授权'],
        'authorization': ['授权'],
        'consents': ['同意'],
        'consent': ['同意'],
        'agreements': ['协议'],
        'agreement': ['协议'],
        'contracts': ['合同'],
        'contract': ['合同'],
        'deals': ['交易'],
        'deal': ['交易'],
        'arrangements': ['安排'],
        'arrangement': ['安排'],
        'setups': ['设置'],
        'setup': ['设置'],
        'installations': ['安装'],
        'installation': ['安装'],
        'configurations': ['配置'],
        'configuration': ['配置'],
        'settings': ['设置'],
        'setting': ['设置'],
        'preferences': ['偏好'],
        'preference': ['偏好'],
        'options': ['选项'],
        'option': ['选项'],
        'choices': ['选择'],
        'choice': ['选择'],
        'alternatives': ['替代'],
        'alternative': ['替代'],
        'possibilities': ['可能'],
        'possibility': ['可能'],
        'opportunities': ['机会'],
        'opportunity': ['机会'],
        'chances': ['机会'],
        'chance': ['机会'],
        'prospects': ['前景'],
        'prospect': ['前景'],
        'potential': ['潜力'],
        'capacities': ['能力'],
        'capacity': ['能力'],
        'capabilities': ['能力'],
        'capability': ['能力'],
        'abilities': ['能力'],
        'ability': ['能力'],
        'skills': ['技能'],
        'skill': ['技能'],
        'competencies': ['能力'],
        'competency': ['能力'],
        'talents': ['才华'],
        'talent': ['才华'],
        'gifts': ['天赋'],
        'gift': ['天赋'],
        'aptitudes': ['天资'],
        'aptitude': ['天资'],
        'knacks': ['诀窍'],
        'knack': ['诀窍'],
        'flairs': ['天资'],
        'flair': ['天资'],
        'bents': ['倾向'],
        'bent': ['倾向'],
        'leanings': ['倾向'],
        'leaning': ['倾向'],
        'inclinations': ['倾向'],
        'inclination': ['倾向'],
        'tendencies': ['趋势'],
        'tendency': ['趋势'],
        'propensities': ['倾向'],
        'propensity': ['倾向'],
        'predispositions': ['倾向'],
        'predisposition': ['倾向'],
        'biases': ['偏见'],
        'bias': ['偏见'],
        'prejudices': ['偏见'],
        'prejudice': ['偏见'],
        'predilections': ['偏爱'],
        'predilection': ['偏爱'],
        'preferences': ['偏好'],
        'preference': ['偏好'],
        'likings': ['喜好'],
        'liking': ['喜好'],
        'fondness': ['喜好'],
        'fond': ['喜好'],
        'affinities': ['亲和力'],
        'affinity': ['亲和力'],
        'attractions': ['吸引力'],
        'attraction': ['吸引力'],
        'appeals': ['吸引力'],
        'appeal': ['吸引力'],
        'allurements': ['诱惑'],
        'allurement': ['诱惑'],
        'fascinators': ['迷人'],
        'fascinator': ['迷人'],
        'charms': ['魅力'],
        'charm': ['魅力'],
        'enchantments': ['魅力'],
        'enchantment': ['魅力'],
        'spells': ['咒语'],
        'spell': ['咒语'],
        'magic': ['魔法'],
        'magics': ['魔法'],
        'wonders': ['奇迹'],
        'wonder': ['奇迹'],
        'marvels': ['奇迹'],
        'marvel': ['奇迹'],
        'miracles': ['奇迹'],
        'miracle': ['奇迹'],
        'phenomena': ['现象'],
        'phenomenon': ['现象'],
        'occurrences': ['事件'],
        'occurrence': ['事件'],
        'happenings': ['事件'],
        'happening': ['事件'],
        'events': ['事件'],
        'event': ['事件'],
        'incidents': ['事件'],
        'incident': ['事件'],
        'episodes': ['事件'],
        'episode': ['事件'],
        'scenes': ['场景'],
        'scene': ['场景'],
        'situations': ['情况'],
        'situation': ['情况'],
        'circumstances': ['情况'],
        'circumstance': ['情况'],
        'conditions': ['条件'],
        'condition': ['条件'],
        'states': ['状态'],
        'state': ['状态'],
        'statuses': ['状态'],
        'status': ['状态'],
        'positions': ['位置'],
        'position': ['位置'],
        'locations': ['位置'],
        'location': ['位置'],
        'places': ['地方'],
        'place': ['地方'],
        'spots': ['地点'],
        'spot': ['地点'],
        'sites': ['地点'],
        'site': ['地点'],
        'sites': ['地点'],
        'site': ['地点'],
        'areas': ['区域'],
        'area': ['区域'],
        'regions': ['区域'],
        'region': ['区域'],
        'zones': ['区域'],
        'zone': ['区域'],
        'sectors': ['区域'],
        'sector': ['区域'],
        'districts': ['区域'],
        'district': ['区域'],
        'quarters': ['区域'],
        'quarter': ['区域'],
        'precincts': ['区域'],
        'precinct': ['区域'],
        'neighborhoods': ['社区'],
        'neighborhood': ['社区'],
        'communities': ['社区'],
        'community': ['社区'],
        'societies': ['社会'],
        'society': ['社会'],
        'civilizations': ['文明'],
        'civilization': ['文明'],
        'cultures': ['文化'],
        'culture': ['文化'],
        'traditions': ['传统'],
        'tradition': ['传统'],
        'customs': ['习俗'],
        'custom': ['习俗'],
        'habits': ['习惯'],
        'habit': ['习惯'],
        'practices': ['实践'],
        'practice': ['实践'],
        'routines': ['常规'],
        'routine': ['常规'],
        'procedures': ['过程'],
        'procedure': ['过程'],
        'protocols': ['协议'],
        'protocol': ['协议'],
        'standards': ['标准'],
        'standard': ['标准'],
        'norms': ['规范'],
        'norm': ['规范'],
        'rules': ['规则'],
        'rule': ['规则'],
        'laws': ['法律'],
        'law': ['法律'],
        'regulations': ['规章'],
        'regulation': ['规章'],
        'statutes': ['法规'],
        'statute': ['法规'],
        'codes': ['代码'],
        'code': ['代码'],
        'acts': ['法案'],
        'act': ['法案'],
        'bills': ['法案'],
        'bill': ['法案'],
        'measures': ['措施'],
        'measure': ['措施'],
        'policies': ['政策'],
        'policy': ['政策'],
        'strategies': ['策略'],
        'strategy': ['策略'],
        'tactics': ['策略'],
        'tactic': ['策略'],
        'approaches': ['方法'],
        'approach': ['方法'],
        'methods': ['方法'],
        'method': ['方法'],
        'techniques': ['技术'],
        'technique': ['技术'],
        'skills': ['技能'],
        'skill': ['技能'],
        'abilities': ['能力'],
        'ability': ['能力'],
        'capabilities': ['能力'],
        'capability': ['能力'],
        'competencies': ['能力'],
        'competency': ['能力'],
        'proficiencies': ['熟练'],
        'proficiency': ['熟练'],
        'expertises': ['专长'],
        'expertise': ['专长'],
        'knowledges': ['知识'],
        'knowledge': ['知识'],
        'understandings': ['理解'],
        'understanding': ['理解'],
        'comprehensions': ['理解'],
        'comprehension': ['理解'],
        'grasps': ['掌握'],
        'grasp': ['掌握'],
        'mastery': ['掌握'],
        'masterys': ['掌握'],
        'command': ['掌握'],
        'commands': ['掌握'],
        'control': ['控制'],
        'controls': ['控制'],
        'management': ['管理'],
        'managements': ['管理'],
        'administration': ['管理'],
        'administrations': ['管理'],
        'governance': ['治理'],
        'governances': ['治理'],
        'leadership': ['领导力'],
        'leaderships': ['领导力'],
        'direction': ['方向'],
        'directions': ['方向'],
        'guidance': ['指导'],
        'guidances': ['指导'],
        'supervision': ['监督'],
        'supervisions': ['监督'],
        'oversight': ['监督'],
        'oversights': ['监督'],
        'monitoring': ['监控'],
        'monitorings': ['监控'],
        'tracking': ['跟踪'],
        'trackings': ['跟踪'],
        'following': ['跟随'],
        'followings': ['跟随'],
        'pursuing': ['追求'],
        'pursuits': ['追求'],
        'chasing': ['追逐'],
        'chasings': ['追逐'],
        'hunting': ['打猎'],
        'huntings': ['打猎'],
        'searching': ['搜索'],
        'searchings': ['搜索'],
        'seeking': ['寻找'],
        'seekings': ['寻找'],
        'looking': ['寻找'],
        'lookings': ['寻找'],
        'finding': ['发现'],
        'findings': ['发现'],
        'discovering': ['发现'],
        'discoverings': ['发现'],
        'uncovering': ['揭露'],
        'uncoverings': ['揭露'],
        'revealing': ['揭示'],
        'revealings': ['揭示'],
        'disclosing': ['披露'],
        'disclosings': ['披露'],
        'exposing': ['暴露'],
        'exposings': ['暴露'],
        'unveiling': ['揭幕'],
        'unveilings': ['揭幕'],
        'showing': ['展示'],
        'showings': ['展示'],
        'displaying': ['展示'],
        'displayings': ['展示'],
        'presenting': ['呈现'],
        'presentings': ['呈现'],
        'exhibiting': ['展示'],
        'exhibitions': ['展示'],
        'demonstrating': ['演示'],
        'demonstrations': ['演示'],
        'illustrating': ['说明'],
        'illustrations': ['说明'],
        'depicting': ['描述'],
        'depictions': ['描述'],
        'portraying': ['描述'],
        'portrayals': ['描述'],
        'representing': ['代表'],
        'representations': ['代表'],
        'signifying': ['表示'],
        'significations': ['表示'],
        'symbolizing': ['象征'],
        'symbolizations': ['象征'],
        'embodying': ['体现'],
        'embodiments': ['体现'],
        'manifesting': ['表现'],
        'manifestations': ['表现'],
        'expressing': ['表达'],
        'expressions': ['表达'],
        'communicating': ['沟通'],
        'communications': ['沟通'],
        'conveying': ['传达'],
        'conveyings': ['传达'],
        'transmitting': ['传输'],
        'transmissions': ['传输'],
        'sending': ['发送'],
        'sendings': ['发送'],
        'delivering': ['交付'],
        'deliveries': ['交付'],
        'transferring': ['转移'],
        'transfers': ['转移'],
        'transporting': ['运输'],
        'transportations': ['运输'],
        'carrying': ['携带'],
        'carries': ['携带'],
        'bearing': ['承载'],
        'bearings': ['承载'],
        'supporting': ['支持'],
        'supportings': ['支持'],
        'sustaining': ['维持'],
        'sustainings': ['维持'],
        'maintaining': ['维护'],
        'maintenances': ['维护'],
        'preserving': ['保护'],
        'preservations': ['保护'],
        'conserving': ['保存'],
        'conservations': ['保存'],
        'protecting': ['保护'],
        'protections': ['保护'],
        'defending': ['防守'],
        'defendings': ['防守'],
        'guarding': ['守卫'],
        'guardings': ['守卫'],
        'shielding': ['屏蔽'],
        'shieldings': ['屏蔽'],
        'covering': ['覆盖'],
        'coverings': ['覆盖'],
        'hiding': ['隐藏'],
        'hidings': ['隐藏'],
        'concealing': ['隐藏'],
        'concealments': ['隐藏'],
        'masking': ['掩码'],
        'maskings': ['掩码'],
        'screening': ['筛选'],
        'screenings': ['筛选'],
        'filtering': ['过滤'],
        'filterings': ['过滤'],
        'sorting': ['排序'],
        'sortings': ['排序'],
        'organizing': ['组织'],
        'organizations': ['组织'],
        'arranging': ['安排'],
        'arrangements': ['安排'],
        'ordering': ['排序'],
        'orderings': ['排序'],
        'sequencing': ['排序'],
        'sequencings': ['排序'],
        'ranking': ['排名'],
        'rankings': ['排名'],
        'rating': ['评级'],
        'ratings': ['评级'],
        'scoring': ['评分'],
        'scorings': ['评分'],
        'grading': ['评分'],
        'gradings': ['评分'],
        'marking': ['评分'],
        'markings': ['评分'],
        'evaluating': ['评估'],
        'evaluations': ['评估'],
        'assessing': ['评估'],
        'assessments': ['评估'],
        'judging': ['判断'],
        'judgings': ['判断'],
        'determining': ['确定'],
        'determinations': ['确定'],
        'deciding': ['决定'],
        'decisions': ['决定'],
        'resolving': ['解决'],
        'resolutions': ['解决'],
        'solving': ['解决'],
        'solutions': ['解决'],
        'fixing': ['修复'],
        'fixings': ['修复'],
        'repairing': ['修复'],
        'repairings': ['修复'],
        'mending': ['修复'],
        'mendings': ['修复'],
        'correcting': ['纠正'],
        'corrections': ['纠正'],
        'rectifying': ['纠正'],
        'rectifications': ['纠正'],
        'adjusting': ['调整'],
        'adjustments': ['调整'],
        'modifying': ['修改'],
        'modifications': ['修改'],
        'altering': ['修改'],
        'alterations': ['修改'],
        'changing': ['改变'],
        'changes': ['改变'],
        'transforming': ['变换'],
        'transformations': ['变换'],
        'converting': ['转换'],
        'conversions': ['转换'],
        'translating': ['翻译'],
        'translations': ['翻译'],
        'interpreting': ['解释'],
        'interpretations': ['解释'],
        'understanding': ['理解'],
        'understandings': ['理解'],
        'comprehending': ['理解'],
        'comprehensions': ['理解'],
        'grasping': ['掌握'],
        'graspings': ['掌握'],
        'learning': ['学习'],
        'learnings': ['学习'],
        'studying': ['研究'],
        'studyings': ['研究'],
        'researching': ['研究'],
        'researchings': ['研究'],
        'investigating': ['调查'],
        'investigations': ['调查'],
        'exploring': ['探索'],
        'explorings': ['探索'],
        'discovering': ['发现'],
        'discoverings': ['发现'],
        'finding': ['发现'],
        'findings': ['发现'],
        'locating': ['定位'],
        'locations': ['定位'],
        'identifying': ['识别'],
        'identifications': ['识别'],
        'recognizing': ['识别'],
        'recognitions': ['识别'],
        'detecting': ['检测'],
        'detections': ['检测'],
        'sensing': ['感应'],
        'sensings': ['感应'],
        'perceiving': ['感知'],
        'perceptions': ['感知'],
        'observing': ['观察'],
        'observations': ['观察'],
        'watching': ['观察'],
        'watchings': ['观察'],
        'viewing': ['查看'],
        'viewings': ['查看'],
        'looking': ['查看'],
        'lookings': ['查看'],
        'seeing': ['看到'],
        'seings': ['看到'],
        'viewing': ['查看'],
        'viewings': ['查看'],
        'examining': ['检查'],
        'examinations': ['检查'],
        'inspecting': ['检查'],
        'inspections': ['检查'],
        'checking': ['检查'],
        'checkings': ['检查'],
        'testing': ['测试'],
        'testings': ['测试'],
        'trying': ['尝试'],
        'tryings': ['尝试'],
        'experimenting': ['实验'],
        'experimentings': ['实验'],
        'attempting': ['尝试'],
        'attempts': ['尝试'],
        'endeavoring': ['努力'],
        'endeavors': ['努力'],
        'striving': ['努力'],
        'strivings': ['努力'],
        'working': ['工作'],
        'workings': ['工作'],
        'operating': ['操作'],
        'operations': ['操作'],
        'functioning': ['运作'],
        'functions': ['运作'],
        'running': ['运行'],
        'runnings': ['运行'],
        'executing': ['执行'],
        'executions': ['执行'],
        'performing': ['执行'],
        'performances': ['执行'],
        'conducting': ['执行'],
        'conductings': ['执行'],
        'carrying': ['携带'],
        'carries': ['携带'],
        'implementing': ['实施'],
        'implementations': ['实施'],
        'applying': ['应用'],
        'applications': ['应用'],
        'using': ['使用'],
        'usings': ['使用'],
        'utilizing': ['利用'],
        'utilizations': ['利用'],
        'employing': ['使用'],
        'employments': ['使用'],
        'deploying': ['部署'],
        'deployments': ['部署'],
        'installing': ['安装'],
        'installations': ['安装'],
        'setting': ['设置'],
        'settings': ['设置'],
        'configuring': ['配置'],
        'configurations': ['配置'],
        'preparing': ['准备'],
        'preparations': ['准备'],
        'organizing': ['组织'],
        'organizations': ['组织'],
        'arranging': ['安排'],
        'arrangements': ['安排'],
        'planning': ['计划'],
        'plannings': ['计划'],
        'designing': ['设计'],
        'designings': ['设计'],
        'developing': ['开发'],
        'developments': ['开发'],
        'creating': ['创建'],
        'creations': ['创建'],
        'building': ['构建'],
        'buildings': ['构建'],
        'constructing': ['构建'],
        'constructions': ['构建'],
        'forming': ['形成'],
        'formings': ['形成'],
        'shaping': ['塑造'],
        'shapings': ['塑造'],
        'molding': ['成型'],
        'moldings': ['成型'],
        'casting': ['铸造'],
        'castings': ['铸造'],
        'forging': ['锻造'],
        'forgings': ['锻造'],
        'sculpting': ['雕刻'],
        'sculptures': ['雕刻'],
        'carving': ['雕刻'],
        'carvings': ['雕刻'],
        'engraving': ['雕刻'],
        'engravings': ['雕刻'],
        'etching': ['蚀刻'],
        'etchings': ['蚀刻'],
        'printing': ['打印'],
        'printings': ['打印'],
        'publishing': ['出版'],
        'publishings': ['出版'],
        'printing': ['印刷'],
        'printings': ['印刷'],
        'producing': ['生产'],
        'productions': ['生产'],
        'manufacturing': ['制造'],
        'manufacturings': ['制造'],
        'fabricating': ['制造'],
        'fabrications': ['制造'],
        'assembling': ['组装'],
        'assemblies': ['组装'],
        'constructing': ['建造'],
        'constructions': ['建造'],
        'erecting': ['竖立'],
        'erections': ['竖立'],
        'raising': ['升起'],
        'raisings': ['升起'],
        'lifting': ['提升'],
        'liftings': ['提升'],
        'elevating': ['提升'],
        'elevations': ['提升'],
        'hoisting': ['升起'],
        'hoistings': ['升起'],
        'boosting': ['提升'],
        'boostings': ['提升'],
        'enhancing': ['增强'],
        'enhancements': ['增强'],
        'improving': ['改进'],
        'improvements': ['改进'],
        'upgrading': ['升级'],
        'upgradings': ['升级'],
        'advancing': ['进步'],
        'advancements': ['进步'],
        'progressing': ['进步'],
        'progressions': ['进步'],
        'developing': ['发展'],
        'developments': ['发展'],
        'growing': ['成长'],
        'growings': ['成长'],
        'expanding': ['扩展'],
        'expansions': ['扩展'],
        'extending': ['扩展'],
        'extensions': ['扩展'],
        'stretching': ['延伸'],
        'stretchings': ['延伸'],
        'reaching': ['到达'],
        'reachings': ['到达'],
        'arriving': ['到达'],
        'arrivals': ['到达'],
        'coming': ['来'],
        'comings': ['来'],
        'approaching': ['接近'],
        'approachings': ['接近'],
        'nearing': ['接近'],
        'nearings': ['接近'],
        'closing': ['关闭'],
        'closings': ['关闭'],
        'ending': ['结束'],
        'endings': ['结束'],
        'finishing': ['完成'],
        'finishings': ['完成'],
        'completing': ['完成'],
        'completions': ['完成'],
        'concluding': ['结论'],
        'conclusions': ['结论'],
        'terminating': ['终止'],
        'terminations': ['终止'],
        'stopping': ['停止'],
        'stoppings': ['停止'],
        'halting': ['停止'],
        'haltings': ['停止'],
        'pausing': ['暂停'],
        'pausings': ['暂停'],
        'resting': ['休息'],
        'restings': ['休息'],
        'waiting': ['等待'],
        'waitings': ['等待'],
        'delaying': ['延迟'],
        'delays': ['延迟'],
        'postponing': ['推迟'],
        'postponings': ['推迟'],
        'deferring': ['推迟'],
        'deferrals': ['推迟'],
        'suspending': ['暂停'],
        'suspensions': ['暂停'],
        'interrupting': ['中断'],
        'interruptions': ['中断'],
        'breaking': ['打破'],
        'breakings': ['打破'],
        'shattering': ['粉碎'],
        'shatterings': ['粉碎'],
        'smashing': ['粉碎'],
        'smashings': ['粉碎'],
        'crushing': ['粉碎'],
        'crushings': ['粉碎'],
        'destroying': ['摧毁'],
        'destroyings': ['摧毁'],
        'demolishing': ['拆除'],
        'demolitions': ['拆除'],
        'dismantling': ['拆除'],
        'dismantlings': ['拆除'],
        'disassembling': ['拆除'],
        'disassemblies': ['拆除'],
        'deconstructing': ['解构'],
        'deconstructions': ['解构'],
        'analyzing': ['分析'],
        'analyzings': ['分析'],
        'examining': ['检查'],
        'examinings': ['检查'],
        'inspecting': ['检查'],
        'inspectings': ['检查'],
        'scrutinizing': ['审查'],
        'scrutinies': ['审查'],
        'reviewing': ['审查'],
        'reviewings': ['审查'],
        'evaluating': ['评估'],
        'evaluations': ['评估'],
        'assessing': ['评估'],
        'assessings': ['评估'],
        'judging': ['判断'],
        'judgings': ['判断'],
        'rating': ['评级'],
        'ratings': ['评级'],
        'ranking': ['排名'],
        'rankings': ['排名'],
        'ordering': ['排序'],
        'orderings': ['排序'],
        'arranging': ['排列'],
        'arrangings': ['排列'],
        'organizing': ['组织'],
        'organizings': ['组织'],
        'structuring': ['构建'],
        'structures': ['构建'],
        'building': ['构建'],
        'buildings': ['构建'],
        'constructing': ['建造'],
        'constructions': ['建造'],
        'erecting': ['建立'],
        'erections': ['建立'],
        'establishing': ['建立'],
        'establishments': ['建立'],
        'founding': ['建立'],
        'foundings': ['建立'],
        'creating': ['创造'],
        'creations': ['创造'],
        'generating': ['生成'],
        'generations': ['生成'],
        'producing': ['生产'],
        'productions': ['生产'],
        'making': ['制造'],
        'makings': ['制造'],
        'fabricating': ['制造'],
        'fabrications': ['制造'],
        'manufacturing': ['制造'],
        'manufacturings': ['制造'],
        'building': ['建造'],
        'buildings': ['建造'],
        'developing': ['发展'],
        'developments': ['发展'],
        'growing': ['发展'],
        'growings': ['发展'],
        'expanding': ['扩展'],
        'expansions': ['扩展'],
        'extending': ['扩展'],
        'extensions': ['扩展'],
        'stretching': ['延伸'],
        'stretchings': ['延伸'],
        'reaching': ['达到'],
        'reachings': ['达到'],
        'attaining': ['达到'],
        'attainments': ['达到'],
        'achieving': ['达到'],
        'achievements': ['达到'],
        'accomplishing': ['达到'],
        'accomplishments': ['达到'],
        'fulfilling': ['实现'],
        'fulfillments': ['实现'],
        'realizing': ['实现'],
        'realizations': ['实现'],
        'actualizing': ['实现'],
        'actualizations': ['实现'],
        'materializing': ['实现'],
        'materializations': ['实现'],
        'manifesting': ['表现'],
        'manifestations': ['表现'],
        'displaying': ['显示'],
        'displayings': ['显示'],
        'showing': ['显示'],
        'showings': ['显示'],
        'demonstrating': ['展示'],
        'demonstrations': ['展示'],
        'illustrating': ['说明'],
        'illustrations': ['说明'],
        'presenting': ['呈现'],
        'presentings': ['呈现'],
        'exhibiting': ['展示'],
        'exhibitions': ['展示'],
        'revealing': ['揭示'],
        'revealings': ['揭示'],
        'disclosing': ['披露'],
        'disclosings': ['披露'],
        'exposing': ['暴露'],
        'exposings': ['暴露'],
        'uncovering': ['揭露'],
        'uncoverings': ['揭露'],
        'unearthing': ['发现'],
        'unearthings': ['发现'],
        'discovering': ['发现'],
        'discoverings': ['发现'],
        'finding': ['找到'],
        'findings': ['找到'],
        'locating': ['定位'],
        'locations': ['定位'],
        'identifying': ['识别'],
        'identifications': ['识别'],
        'recognizing': ['识别'],
        'recognitions': ['识别'],
        'detecting': ['检测'],
        'detections': ['检测'],
        'sensing': ['感知'],
        'sensings': ['感知'],
        'perceiving': ['感知'],
        'perceptions': ['感知'],
        'observing': ['观察'],
        'observations': ['观察'],
        'watching': ['观察'],
        'watchings': ['观察'],
        'viewing': ['查看'],
        'viewings': ['查看'],
        'looking': ['查看'],
        'lookings': ['查看'],
        'seeing': ['看到'],
        'seeings': ['看到'],
        'viewing': ['查看'],
        'viewings': ['查看'],
        'examining': ['检查'],
        'examinings': ['检查'],
        'inspecting': ['检查'],
        'inspectings': ['检查'],
        'checking': ['检查'],
        'checkings': ['检查'],
        'verifying': ['验证'],
        'verifications': ['验证'],
        'validating': ['验证'],
        'validations': ['验证'],
        'confirming': ['确认'],
        'confirmations': ['确认'],
        'corroborating': ['证实'],
        'corroborations': ['证实'],
        'substantiating': ['证实'],
        'substantiations': ['证实'],
        'authenticating': ['认证'],
        'authentications': ['认证'],
        'certifying': ['认证'],
        'certifications': ['认证'],
        'qualifying': ['合格'],
        'qualifications': ['合格'],
        'accrediting': ['认证'],
        'accreditations': ['认证'],
        'endorsing': ['认可'],
        'endorsements': ['认可'],
        'approving': ['批准'],
        'approvals': ['批准'],
        'sanctioning': ['批准'],
        'sanctions': ['批准'],
        'authorizing': ['授权'],
        'authorizations': ['授权'],
        'permitting': ['允许'],
        'permissions': ['允许'],
        'allowing': ['允许'],
        'allowings': ['允许'],
        'enabling': ['启用'],
        'enablings': ['启用'],
        'empowering': ['授权'],
        'empowerings': ['授权'],
        'facilitating': ['促进'],
        'facilitations': ['促进'],
        'helping': ['帮助'],
        'helpings': ['帮助'],
        'assisting': ['协助'],
        'assistances': ['协助'],
        'aiding': ['帮助'],
        'aidings': ['帮助'],
        'supporting': ['支持'],
        'supportings': ['支持'],
        'backing': ['支持'],
        'backings': ['支持'],
        'sponsoring': ['赞助'],
        'sponsorships': ['赞助'],
        'funding': ['资助'],
        'fundings': ['资助'],
        'financing': ['资助'],
        'financings': ['资助'],
        'investing': ['投资'],
        'investments': ['投资'],
        'spending': ['支出'],
        'spendings': ['支出'],
        'expending': ['支出'],
        'expenditures': ['支出'],
        'disbursing': ['支出'],
        'disbursements': ['支出'],
        'paying': ['支付'],
        'payments': ['支付'],
        'remunerating': ['报酬'],
        'remunerations': ['报酬'],
        'compensating': ['补偿'],
        'compensations': ['补偿'],
        'reimbursing': ['补偿'],
        'reimbursements': ['补偿'],
        'refunding': ['补偿'],
        'refundings': ['补偿'],
        'repaying': ['偿还'],
        'repayments': ['偿还'],
        'restituting': ['偿还'],
        'restitutions': ['偿还'],
        'restoring': ['恢复'],
        'restorations': ['恢复'],
        'recovering': ['恢复'],
        'recoverings': ['恢复'],
        'retrieving': ['检索'],
        'retrievals': ['检索'],
        'fetching': ['获取'],
        'fetchings': ['获取'],
        'obtaining': ['获取'],
        'obtainings': ['获取'],
        'acquiring': ['获取'],
        'acquisitions': ['获取'],
        'procuring': ['获取'],
        'procurings': ['获取'],
        'securing': ['获取'],
        'securings': ['获取'],
        'gaining': ['获取'],
        'gainings': ['获取'],
        'earning': ['赚取'],
        'earnings': ['赚取'],
        'making': ['赚取'],
        'makings': ['赚取'],
        'receiving': ['接收'],
        'receivings': ['接收'],
        'accepting': ['接受'],
        'acceptings': ['接受'],
        'taking': ['接受'],
        'takings': ['接受'],
        'getting': ['获取'],
        'gettings': ['获取'],
        'having': ['拥有'],
        'havings': ['拥有'],
        'owning': ['拥有'],
        'ownings': ['拥有'],
        'possessing': ['拥有'],
        'possessions': ['拥有'],
        'holding': ['持有'],
        'holdings': ['持有'],
        'keeping': ['保持'],
        'keepings': ['保持'],
        'retaining': ['保留'],
        'retainings': ['保留'],
        'maintaining': ['维护'],
        'maintenances': ['维护'],
        'preserving': ['保存'],
        'preservations': ['保存'],
        'conserving': ['保护'],
        'conservations': ['保护'],
        'protecting': ['保护'],
        'protections': ['保护'],
        'defending': ['保护'],
        'defendings': ['保护'],
        'shielding': ['保护'],
        'shieldings': ['保护'],
        'guarding': ['保护'],
        'guardings': ['保护'],
        'securing': ['保护'],
        'securings': ['保护'],
        'safeguarding': ['保护'],
        'safeguardings': ['保护'],
        'ensuring': ['保证'],
        'ensurings': ['保证'],
        'guaranteeing': ['保证'],
        'guarantees': ['保证'],
        'assuring': ['保证'],
        'assurances': ['保证'],
        'promising': ['承诺'],
        'promises': ['承诺'],
        'pledging': ['承诺'],
        'pledges': ['承诺'],
        'vowing': ['发誓'],
        'vows': ['发誓'],
        'swearing': ['发誓'],
        'swearings': ['发誓'],
        'affirming': ['肯定'],
        'affirmings': ['肯定'],
        'confirming': ['确认'],
        'confirmations': ['确认'],
        'validating': ['验证'],
        'validations': ['验证'],
        'verifying': ['验证'],
        'verifications': ['验证'],
        'proving': ['证明'],
        'provings': ['证明'],
        'demonstrating': ['证明'],
        'demonstrations': ['证明'],
        'showing': ['展示'],
        'showings': ['展示'],
        'proving': ['证明'],
        'provings': ['证明'],
        'establishing': ['建立'],
        'establishments': ['建立'],
        'setting': ['设置'],
        'settings': ['设置'],
        'determining': ['确定'],
        'determinations': ['确定'],
        'fixing': ['确定'],
        'fixings': ['确定'],
        'settling': ['解决'],
        'settlings': ['解决'],
        'resolving': ['解决'],
        'resolutions': ['解决'],
        'solving': ['解决'],
        'solutions': ['解决'],
        'answering': ['回答'],
        'answers': ['回答'],
        'responding': ['回应'],
        'responses': ['回应'],
        'replying': ['回答'],
        'replies': ['回答'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'going': ['去'],
        'goings': ['去'],
        'leaving': ['离开'],
        'leavings': ['离开'],
        'departing': ['离开'],
        'departings': ['离开'],
        'exiting': ['退出'],
        'exits': ['退出'],
        'withdrawing': ['退出'],
        'withdrawings': ['退出'],
        'retiring': ['退休'],
        'retirements': ['退休'],
        'stepping': ['退出'],
        'steppings': ['退出'],
        'resigning': ['辞职'],
        'resignings': ['辞职'],
        'quitting': ['退出'],
        'quittings': ['退出'],
        'abandoning': ['放弃'],
        'abandonments': ['放弃'],
        'deserting': ['放弃'],
        'desertions': ['放弃'],
        'forsaking': ['放弃'],
        'forsakings': ['放弃'],
        'renouncing': ['放弃'],
        'renunciations': ['放弃'],
        'relinquishing': ['放弃'],
        'relinquishments': ['放弃'],
        'giving': ['给予'],
        'givings': ['给予'],
        'donating': ['捐赠'],
        'donations': ['捐赠'],
        'contributing': ['贡献'],
        'contributions': ['贡献'],
        'providing': ['提供'],
        'providings': ['提供'],
        'supplying': ['供应'],
        'supplyings': ['供应'],
        'delivering': ['交付'],
        'deliveries': ['交付'],
        'handing': ['交付'],
        'handings': ['交付'],
        'passing': ['通过'],
        'passings': ['通过'],
        'transferring': ['转移'],
        'transfers': ['转移'],
        'transmitting': ['传输'],
        'transmissions': ['传输'],
        'conveying': ['传达'],
        'conveyings': ['传达'],
        'communicating': ['沟通'],
        'communications': ['沟通'],
        'expressing': ['表达'],
        'expressions': ['表达'],
        'articulating': ['表达'],
        'articulations': ['表达'],
        'voicing': ['表达'],
        'voicings': ['表达'],
        'uttering': ['表达'],
        'utterings': ['表达'],
        'speaking': ['说话'],
        'speakings': ['说话'],
        'talking': ['说话'],
        'talkings': ['说话'],
        'conversing': ['交谈'],
        'conversations': ['交谈'],
        'discussing': ['讨论'],
        'discussions': ['讨论'],
        'debating': ['辩论'],
        'debatings': ['辩论'],
        'arguing': ['争论'],
        'arguings': ['争论'],
        'contending': ['争论'],
        'contentions': ['争论'],
        'disputing': ['争论'],
        'disputings': ['争论'],
        'quarreling': ['争吵'],
        'quarrels': ['争吵'],
        'fighting': ['斗争'],
        'fightings': ['斗争'],
        'battling': ['斗争'],
        'battles': ['斗争'],
        'combating': ['斗争'],
        'combatings': ['斗争'],
        'warring': ['战争'],
        'warrings': ['战争'],
        'conflicting': ['冲突'],
        'conflicts': ['冲突'],
        'clashing': ['冲突'],
        'clashings': ['冲突'],
        'colliding': ['碰撞'],
        'collisions': ['碰撞'],
        'crashing': ['碰撞'],
        'crashings': ['碰撞'],
        'smashing': ['碰撞'],
        'smashings': ['碰撞'],
        'striking': ['打击'],
        'strikings': ['打击'],
        'hitting': ['打击'],
        'hittings': ['打击'],
        'beating': ['打击'],
        'beatings': ['打击'],
        'pounding': ['打击'],
        'poundings': ['打击'],
        'hammering': ['打击'],
        'hammerings': ['打击'],
        'bashing': ['打击'],
        'bashings': ['打击'],
        'thrashing': ['打击'],
        'thrashings': ['打击'],
        'whipping': ['打击'],
        'whippings': ['打击'],
        'lashing': ['打击'],
        'lashings': ['打击'],
        'flogging': ['鞭打'],
        'floggings': ['鞭打'],
        'scourging': ['鞭打'],
        'scourgings': ['鞭打'],
        'chastising': ['惩罚'],
        'chastisements': ['惩罚'],
        'punishing': ['惩罚'],
        'punishments': ['惩罚'],
        'penalizing': ['惩罚'],
        'penalizations': ['惩罚'],
        'disciplining': ['训练'],
        'disciplinings': ['训练'],
        'training': ['训练'],
        'trainings': ['训练'],
        'teaching': ['教学'],
        'teachings': ['教学'],
        'instructing': ['指导'],
        'instructions': ['指导'],
        'educating': ['教育'],
        'educations': ['教育'],
        'schooling': ['教育'],
        'schoolings': ['教育'],
        'tutoring': ['辅导'],
        'tutorings': ['辅导'],
        'coaching': ['辅导'],
        'coachings': ['辅导'],
        'mentoring': ['指导'],
        'mentorings': ['指导'],
        'guiding': ['指导'],
        'guidings': ['指导'],
        'directing': ['指导'],
        'directions': ['指导'],
        'leading': ['领导'],
        'leadings': ['领导'],
        'managing': ['管理'],
        'managements': ['管理'],
        'administering': ['管理'],
        'administrations': ['管理'],
        'governing': ['治理'],
        'governings': ['治理'],
        'ruling': ['统治'],
        'rulings': ['统治'],
        'commanding': ['命令'],
        'commandings': ['命令'],
        'ordering': ['命令'],
        'orderings': ['命令'],
        'directing': ['指导'],
        'directions': ['指导'],
        'instructing': ['指示'],
        'instructions': ['指示'],
        'telling': ['告诉'],
        'tellings': ['告诉'],
        'informing': ['通知'],
        'informings': ['通知'],
        'notifying': ['通知'],
        'notifications': ['通知'],
        'announcing': ['宣布'],
        'announcements': ['宣布'],
        'declaring': ['宣布'],
        'declarations': ['宣布'],
        'proclaiming': ['宣布'],
        'proclamations': ['宣布'],
        'stating': ['声明'],
        'statements': ['声明'],
        'asserting': ['声明'],
        'assertions': ['声明'],
        'claiming': ['声明'],
        'claimings': ['声明'],
        'alleging': ['声称'],
        'allegations': ['声称'],
        'maintaining': ['坚持'],
        'maintenances': ['坚持'],
        'insisting': ['坚持'],
        'insistings': ['坚持'],
        'contending': ['坚持'],
        'contentions': ['坚持'],
        'arguing': ['主张'],
        'arguings': ['主张'],
        'suggesting': ['建议'],
        'suggestions': ['建议'],
        'proposing': ['提议'],
        'proposals': ['提议'],
        'recommending': ['推荐'],
        'recommendations': ['推荐'],
        'advising': ['建议'],
        'advisings': ['建议'],
        'counseling': ['咨询'],
        'counselings': ['咨询'],
        'consulting': ['咨询'],
        'consultations': ['咨询'],
        'seeking': ['寻求'],
        'seekings': ['寻求'],
        'looking': ['寻找'],
        'lookings': ['寻找'],
        'searching': ['搜索'],
        'searchings': ['搜索'],
        'hunting': ['狩猎'],
        'huntings': ['狩猎'],
        'chasing': ['追逐'],
        'chasings': ['追逐'],
        'pursuing': ['追求'],
        'pursuits': ['追求'],
        'following': ['跟随'],
        'followings': ['跟随'],
        'tracking': ['跟踪'],
        'trackings': ['跟踪'],
        'tracing': ['跟踪'],
        'tracings': ['跟踪'],
        'monitoring': ['监控'],
        'monitorings': ['监控'],
        'observing': ['观察'],
        'observations': ['观察'],
        'watching': ['观察'],
        'watchings': ['观察'],
        'viewing': ['观察'],
        'viewings': ['观察'],
        'surveying': ['调查'],
        'surveys': ['调查'],
        'studying': ['研究'],
        'studyings': ['研究'],
        'researching': ['研究'],
        'researchings': ['研究'],
        'investigating': ['调查'],
        'investigations': ['调查'],
        'examining': ['检查'],
        'examinations': ['检查'],
        'inspecting': ['检查'],
        'inspections': ['检查'],
        'checking': ['检查'],
        'checkings': ['检查'],
        'testing': ['测试'],
        'testings': ['测试'],
        'trying': ['尝试'],
        'tryings': ['尝试'],
        'attempting': ['尝试'],
        'attempts': ['尝试'],
        'endeavoring': ['努力'],
        'endeavors': ['努力'],
        'striving': ['努力'],
        'strivings': ['努力'],
        'working': ['工作'],
        'workings': ['工作'],
        'laboring': ['工作'],
        'laborings': ['工作'],
        'toiling': ['工作'],
        'toilings': ['工作'],
        'slaving': ['工作'],
        'slavings': ['工作'],
        'drudging': ['工作'],
        'drudgings': ['工作'],
        'grinding': ['研磨'],
        'grindings': ['研磨'],
        'milling': ['碾磨'],
        'millings': ['碾磨'],
        'crushing': ['压碎'],
        'crushings': ['压碎'],
        'pulverizing': ['粉碎'],
        'pulverizations': ['粉碎'],
        'shattering': ['粉碎'],
        'shatterings': ['粉碎'],
        'smashing': ['粉碎'],
        'smashings': ['粉碎'],
        'breaking': ['破碎'],
        'breakings': ['破碎'],
        'fracturing': ['断裂'],
        'fractures': ['断裂'],
        'cracking': ['裂纹'],
        'crackings': ['裂纹'],
        'splitting': ['分裂'],
        'splittings': ['分裂'],
        'dividing': ['分裂'],
        'dividings': ['分裂'],
        'separating': ['分离'],
        'separatings': ['分离'],
        'parting': ['分离'],
        'partings': ['分离'],
        'detaching': ['分离'],
        'detachments': ['分离'],
        'disconnecting': ['断开'],
        'disconnectings': ['断开'],
        'unlinking': ['断开'],
        'unlinkings': ['断开'],
        'untying': ['解开'],
        'untyings': ['解开'],
        'unbinding': ['解开'],
        'unbindings': ['解开'],
        'unfastening': ['解开'],
        'unfastenings': ['解开'],
        'unclasping': ['解开'],
        'unclaspings': ['解开'],
        'unhooking': ['解开'],
        'unhookings': ['解开'],
        'unlatching': ['解开'],
        'unlatchings': ['解开'],
        'unbolting': ['解开'],
        'unboltings': ['解开'],
        'unlocking': ['解锁'],
        'unlockings': ['解锁'],
        'opening': ['打开'],
        'openings': ['打开'],
        'uncovering': ['揭开'],
        'uncoverings': ['揭开'],
        'unveiling': ['揭开'],
        'unveilings': ['揭开'],
        'unmasking': ['揭开'],
        'unmaskings': ['揭开'],
        'unwrapping': ['解开'],
        'unwrappings': ['解开'],
        'unfolding': ['展开'],
        'unfoldings': ['展开'],
        'unrolling': ['展开'],
        'unrollings': ['展开'],
        'unfurling': ['展开'],
        'unfurlings': ['展开'],
        'unraveling': ['解开'],
        'unravelings': ['解开'],
        'untangling': ['解开'],
        'untanglings': ['解开'],
        'unruffling': ['解开'],
        'unrufflings': ['解开'],
        'unscrambling': ['解密'],
        'unscramblings': ['解密'],
        'decoding': ['解码'],
        'decodings': ['解码'],
        'decrypting': ['解密'],
        'decryptions': ['解密'],
        'deciphering': ['破译'],
        'decipherings': ['破译'],
        'interpreting': ['解释'],
        'interpretations': ['解释'],
        'translating': ['翻译'],
        'translations': ['翻译'],
        'rendering': ['渲染'],
        'renderings': ['渲染'],
        'converting': ['转换'],
        'conversions': ['转换'],
        'transforming': ['变换'],
        'transformations': ['变换'],
        'changing': ['改变'],
        'changes': ['改变'],
        'modifying': ['修改'],
        'modifications': ['修改'],
        'altering': ['改变'],
        'alterations': ['改变'],
        'adjusting': ['调整'],
        'adjustments': ['调整'],
        'tuning': ['调整'],
        'tunings': ['调整'],
        'regulating': ['调节'],
        'regulations': ['调节'],
        'controlling': ['控制'],
        'controllings': ['控制'],
        'managing': ['管理'],
        'managements': ['管理'],
        'directing': ['指导'],
        'directions': ['指导'],
        'guiding': ['指导'],
        'guidings': ['指导'],
        'steering': ['引导'],
        'steerings': ['引导'],
        'piloting': ['驾驶'],
        'pilotings': ['驾驶'],
        'navigating': ['导航'],
        'navigations': ['导航'],
        'sailing': ['航行'],
        'sailings': ['航行'],
        'flying': ['飞行'],
        'flyings': ['飞行'],
        'soaring': ['翱翔'],
        'soarings': ['翱翔'],
        'gliding': ['滑翔'],
        'glidings': ['滑翔'],
        'floating': ['漂浮'],
        'floatings': ['漂浮'],
        'drifting': ['漂流'],
        'driftings': ['漂流'],
        'wandering': ['漫游'],
        'wanderings': ['漫游'],
        'roaming': ['漫游'],
        'roamings': ['漫游'],
        'rambling': ['漫游'],
        'ramblings': ['漫游'],
        'strolling': ['漫步'],
        'strollings': ['漫步'],
        'walking': ['散步'],
        'walkings': ['散步'],
        'hiking': ['远足'],
        'hikings': ['远足'],
        'trekking': ['跋涉'],
        'trekkings': ['跋涉'],
        'marching': ['行军'],
        'marchings': ['行军'],
        'parading': ['游行'],
        'paradings': ['游行'],
        'strutting': ['昂首阔步'],
        'struttings': ['昂首阔步'],
        'swaggering': ['昂首阔步'],
        'swaggerings': ['昂首阔步'],
        'striding': ['大步走'],
        'stridings': ['大步走'],
        'stepping': ['踏步'],
        'steppings': ['踏步'],
        'treading': ['踏步'],
        'treadings': ['踏步'],
        'pacing': ['步调'],
        'pacings': ['步调'],
        'measuring': ['测量'],
        'measurings': ['测量'],
        'gauging': ['测量'],
        'gaugings': ['测量'],
        'estimating': ['估算'],
        'estimations': ['估算'],
        'calculating': ['计算'],
        'calculations': ['计算'],
        'computing': ['计算'],
        'computings': ['计算'],
        'figuring': ['计算'],
        'figurings': ['计算'],
        'working': ['计算'],
        'workings': ['计算'],
        'solving': ['求解'],
        'solvings': ['求解'],
        'answering': ['回答'],
        'answers': ['回答'],
        'responding': ['响应'],
        'responses': ['响应'],
        'reacting': ['反应'],
        'reactions': ['反应'],
        'acting': ['行动'],
        'actings': ['行动'],
        'performing': ['执行'],
        'performances': ['执行'],
        'doing': ['做'],
        'doings': ['做'],
        'making': ['制造'],
        'makings': ['制造'],
        'creating': ['创造'],
        'creations': ['创造'],
        'building': ['构建'],
        'buildings': ['构建'],
        'constructing': ['建造'],
        'constructions': ['建造'],
        'forming': ['形成'],
        'formings': ['形成'],
        'shaping': ['塑造'],
        'shapings': ['塑造'],
        'molding': ['塑造'],
        'moldings': ['塑造'],
        'modeling': ['建模'],
        'modelings': ['建模'],
        'simulating': ['模拟'],
        'simulations': ['模拟'],
        'imitating': ['模仿'],
        'imitations': ['模仿'],
        'copying': ['复制'],
        'copyings': ['复制'],
        'duplicating': ['复制'],
        'duplications': ['复制'],
        'replicating': ['复制'],
        'replications': ['复制'],
        'reproducing': ['复制'],
        'reproductions': ['复制'],
        'cloning': ['克隆'],
        'clonings': ['克隆'],
        'mirroring': ['镜像'],
        'mirrorings': ['镜像'],
        'reflecting': ['反射'],
        'reflections': ['反射'],
        'bouncing': ['弹跳'],
        'bouncings': ['弹跳'],
        'rebounding': ['弹回'],
        'reboundings': ['弹回'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'recovering': ['恢复'],
        'recoverings': ['恢复'],
        'restoring': ['恢复'],
        'restorations': ['恢复'],
        'rebuilding': ['重建'],
        'rebuildings': ['重建'],
        'reconstructing': ['重建'],
        'reconstructions': ['重建'],
        'recreating': ['重建'],
        'recreations': ['重建'],
        'renewing': ['更新'],
        'renewals': ['更新'],
        'refreshing': ['刷新'],
        'refreshings': ['刷新'],
        'reviving': ['恢复'],
        'revivals': ['恢复'],
        'resurrecting': ['复活'],
        'resurrections': ['复活'],
        'awakening': ['唤醒'],
        'awakenings': ['唤醒'],
        'arousing': ['唤醒'],
        'arousings': ['唤醒'],
        'stimulating': ['刺激'],
        'stimulations': ['刺激'],
        'exciting': ['激发'],
        'excitings': ['激发'],
        'thrilling': ['兴奋'],
        'thrillings': ['兴奋'],
        'electrifying': ['兴奋'],
        'electrifications': ['兴奋'],
        'inspiring': ['启发'],
        'inspirations': ['启发'],
        'motivating': ['激励'],
        'motivations': ['激励'],
        'encouraging': ['鼓励'],
        'encouragements': ['鼓励'],
        'heartening': ['鼓舞'],
        'heartenings': ['鼓舞'],
        'cheering': ['欢呼'],
        'cheerings': ['欢呼'],
        'uplifting': ['提升'],
        'upliftings': ['提升'],
        'elevating': ['提升'],
        'elevations': ['提升'],
        'raising': ['提高'],
        'raisings': ['提高'],
        'lifting': ['举起'],
        'liftings': ['举起'],
        'hoisting': ['举起'],
        'hoistings': ['举起'],
        'boosting': ['提高'],
        'boostings': ['提高'],
        'enhancing': ['增强'],
        'enhancements': ['增强'],
        'improving': ['改进'],
        'improvements': ['改进'],
        'bettering': ['改善'],
        'betterings': ['改善'],
        'amending': ['修正'],
        'amendings': ['修正'],
        'correcting': ['纠正'],
        'corrections': ['纠正'],
        'fixing': ['修复'],
        'fixings': ['修复'],
        'repairing': ['修复'],
        'repairings': ['修复'],
        'mending': ['修复'],
        'mendings': ['修复'],
        'patching': ['修补'],
        'patchings': ['修补'],
        'darning': ['修补'],
        'darnings': ['修补'],
        'stitching': ['缝合'],
        'stitchings': ['缝合'],
        'sewing': ['缝制'],
        'sewings': ['缝制'],
        'knitting': ['编织'],
        'knittings': ['编织'],
        'weaving': ['编织'],
        'weavings': ['编织'],
        'spinning': ['纺纱'],
        'spinnings': ['纺纱'],
        'twisting': ['扭曲'],
        'twistings': ['扭曲'],
        'turning': ['转动'],
        'turnings': ['转动'],
        'rotating': ['旋转'],
        'rotations': ['旋转'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'circling': ['旋转'],
        'circlings': ['旋转'],
        'orbiting': ['轨道'],
        'orbitings': ['轨道'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'gyrating': ['旋转'],
        'gyrations': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'edying': ['旋转'],
        'edyings': ['旋转'],
        'vortexing': ['旋转'],
        'vortexings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'rotating': ['旋转'],
        'rotations': ['旋转'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'gyrating': ['旋转'],
        'gyrations': ['旋转'],
        'cycling': ['循环'],
        'cyclings': ['循环'],
        'looping': ['循环'],
        'loopings': ['循环'],
        'iterating': ['迭代'],
        'iterations': ['迭代'],
        'repeating': ['重复'],
        'repeatings': ['重复'],
        'recurring': ['重复'],
        'recurrings': ['重复'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'restoring': ['恢复'],
        'restorations': ['恢复'],
        'recovering': ['恢复'],
        'recoverings': ['恢复'],
        'retrieving': ['检索'],
        'retrievals': ['检索'],
        'fetching': ['获取'],
        'fetchings': ['获取'],
        'obtaining': ['获取'],
        'obtainings': ['获取'],
        'acquiring': ['获取'],
        'acquisitions': ['获取'],
        'procuring': ['获取'],
        'procurings': ['获取'],
        'securing': ['获取'],
        'securings': ['获取'],
        'gaining': ['获取'],
        'gainings': ['获取'],
        'earning': ['获得'],
        'earnings': ['获得'],
        'making': ['获得'],
        'makings': ['获得'],
        'winning': ['赢得'],
        'winnings': ['赢得'],
        'achieving': ['实现'],
        'achievements': ['实现'],
        'accomplishing': ['实现'],
        'accomplishments': ['实现'],
        'fulfilling': ['实现'],
        'fulfillments': ['实现'],
        'realizing': ['实现'],
        'realizations': ['实现'],
        'actualizing': ['实现'],
        'actualizations': ['实现'],
        'materializing': ['实现'],
        'materializations': ['实现'],
        'manifesting': ['表现'],
        'manifestations': ['表现'],
        'displaying': ['显示'],
        'displayings': ['显示'],
        'showing': ['显示'],
        'showings': ['显示'],
        'demonstrating': ['证明'],
        'demonstrations': ['证明'],
        'proving': ['证明'],
        'provings': ['证明'],
        'establishing': ['确立'],
        'establishments': ['确立'],
        'setting': ['设置'],
        'settings': ['设置'],
        'determining': ['确定'],
        'determinations': ['确定'],
        'fixing': ['确定'],
        'fixings': ['确定'],
        'settling': ['解决'],
        'settlings': ['解决'],
        'resolving': ['解决'],
        'resolutions': ['解决'],
        'solving': ['解决'],
        'solutions': ['解决'],
        'answering': ['回答'],
        'answers': ['回答'],
        'responding': ['回应'],
        'responses': ['回应'],
        'replying': ['回答'],
        'replies': ['回答'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'going': ['去'],
        'goings': ['去'],
        'leaving': ['离开'],
        'leavings': ['离开'],
        'departing': ['离开'],
        'departings': ['离开'],
        'exiting': ['退出'],
        'exits': ['退出'],
        'withdrawing': ['退出'],
        'withdrawings': ['退出'],
        'retiring': ['退休'],
        'retirements': ['退休'],
        'stepping': ['退出'],
        'steppings': ['退出'],
        'resigning': ['辞职'],
        'resignings': ['辞职'],
        'quitting': ['退出'],
        'quittings': ['退出'],
        'abandoning': ['放弃'],
        'abandonments': ['放弃'],
        'deserting': ['放弃'],
        'desertions': ['放弃'],
        'forsaking': ['放弃'],
        'forsakings': ['放弃'],
        'renouncing': ['放弃'],
        'renunciations': ['放弃'],
        'relinquishing': ['放弃'],
        'relinquishments': ['放弃'],
        'giving': ['给予'],
        'givings': ['给予'],
        'donating': ['捐赠'],
        'donations': ['捐赠'],
        'contributing': ['贡献'],
        'contributions': ['贡献'],
        'providing': ['提供'],
        'providings': ['提供'],
        'supplying': ['供应'],
        'supplyings': ['供应'],
        'delivering': ['交付'],
        'deliveries': ['交付'],
        'handing': ['交付'],
        'handings': ['交付'],
        'passing': ['传递'],
        'passings': ['传递'],
        'transferring': ['转移'],
        'transfers': ['转移'],
        'transmitting': ['传输'],
        'transmissions': ['传输'],
        'conveying': ['传达'],
        'conveyings': ['传达'],
        'communicating': ['沟通'],
        'communications': ['沟通'],
        'expressing': ['表达'],
        'expressions': ['表达'],
        'articulating': ['表达'],
        'articulations': ['表达'],
        'voicing': ['表达'],
        'voicings': ['表达'],
        'uttering': ['表达'],
        'utterings': ['表达'],
        'speaking': ['说话'],
        'speakings': ['说话'],
        'talking': ['说话'],
        'talkings': ['说话'],
        'conversing': ['交谈'],
        'conversations': ['交谈'],
        'discussing': ['讨论'],
        'discussions': ['讨论'],
        'debating': ['辩论'],
        'debatings': ['辩论'],
        'arguing': ['争论'],
        'arguings': ['争论'],
        'contending': ['争论'],
        'contentions': ['争论'],
        'disputing': ['争论'],
        'disputings': ['争论'],
        'quarreling': ['争吵'],
        'quarrels': ['争吵'],
        'fighting': ['战斗'],
        'fightings': ['战斗'],
        'battling': ['战斗'],
        'battles': ['战斗'],
        'combating': ['战斗'],
        'combatings': ['战斗'],
        'warring': ['战争'],
        'warrings': ['战争'],
        'conflicting': ['冲突'],
        'conflicts': ['冲突'],
        'clashing': ['冲突'],
        'clashings': ['冲突'],
        'colliding': ['碰撞'],
        'collisions': ['碰撞'],
        'crashing': ['碰撞'],
        'crashings': ['碰撞'],
        'smashing': ['碰撞'],
        'smashings': ['碰撞'],
        'striking': ['打击'],
        'strikings': ['打击'],
        'hitting': ['打击'],
        'hittings': ['打击'],
        'beating': ['打击'],
        'beatings': ['打击'],
        'pounding': ['打击'],
        'poundings': ['打击'],
        'hammering': ['打击'],
        'hammerings': ['打击'],
        'bashing': ['打击'],
        'bashings': ['打击'],
        'thrashing': ['打击'],
        'thrashings': ['打击'],
        'whipping': ['鞭打'],
        'whippings': ['鞭打'],
        'lashing': ['鞭打'],
        'lashings': ['鞭打'],
        'flogging': ['鞭打'],
        'floggings': ['鞭打'],
        'scourging': ['鞭打'],
        'scourgings': ['鞭打'],
        'chastising': ['惩罚'],
        'chastisements': ['惩罚'],
        'punishing': ['惩罚'],
        'punishments': ['惩罚'],
        'penalizing': ['惩罚'],
        'penalizations': ['惩罚'],
        'disciplining': ['训练'],
        'disciplinings': ['训练'],
        'training': ['训练'],
        'trainings': ['训练'],
        'teaching': ['教学'],
        'teachings': ['教学'],
        'instructing': ['指导'],
        'instructions': ['指导'],
        'educating': ['教育'],
        'educations': ['教育'],
        'schooling': ['教育'],
        'schoolings': ['教育'],
        'tutoring': ['辅导'],
        'tutorings': ['辅导'],
        'coaching': ['辅导'],
        'coachings': ['辅导'],
        'mentoring': ['指导'],
        'mentorings': ['指导'],
        'guiding': ['指导'],
        'guidings': ['指导'],
        'directing': ['指导'],
        'directions': ['指导'],
        'leading': ['领导'],
        'leadings': ['领导'],
        'managing': ['管理'],
        'managements': ['管理'],
        'administering': ['管理'],
        'administrations': ['管理'],
        'governing': ['治理'],
        'governings': ['治理'],
        'ruling': ['统治'],
        'rulings': ['统治'],
        'commanding': ['命令'],
        'commandings': ['命令'],
        'ordering': ['命令'],
        'orderings': ['命令'],
        'directing': ['指导'],
        'directions': ['指导'],
        'instructing': ['指示'],
        'instructions': ['指示'],
        'telling': ['告诉'],
        'tellings': ['告诉'],
        'informing': ['通知'],
        'informings': ['通知'],
        'notifying': ['通知'],
        'notifications': ['通知'],
        'announcing': ['宣布'],
        'announcements': ['宣布'],
        'declaring': ['宣布'],
        'declarations': ['宣布'],
        'proclaiming': ['宣布'],
        'proclamations': ['宣布'],
        'stating': ['声明'],
        'statements': ['声明'],
        'asserting': ['声明'],
        'assertions': ['声明'],
        'claiming': ['声明'],
        'claimings': ['声明'],
        'alleging': ['声称'],
        'allegations': ['声称'],
        'maintaining': ['维持'],
        'maintenances': ['维持'],
        'insisting': ['坚持'],
        'insistings': ['坚持'],
        'contending': ['坚持'],
        'contentions': ['坚持'],
        'arguing': ['主张'],
        'arguings': ['主张'],
        'suggesting': ['建议'],
        'suggestions': ['建议'],
        'proposing': ['提议'],
        'proposals': ['提议'],
        'recommending': ['推荐'],
        'recommendations': ['推荐'],
        'advising': ['建议'],
        'advisings': ['建议'],
        'counseling': ['咨询'],
        'counselings': ['咨询'],
        'consulting': ['咨询'],
        'consultations': ['咨询'],
        'seeking': ['寻求'],
        'seekings': ['寻求'],
        'looking': ['寻找'],
        'lookings': ['寻找'],
        'searching': ['搜索'],
        'searchings': ['搜索'],
        'hunting': ['狩猎'],
        'huntings': ['狩猎'],
        'chasing': ['追逐'],
        'chasings': ['追逐'],
        'pursuing': ['追求'],
        'pursuits': ['追求'],
        'following': ['跟随'],
        'followings': ['跟随'],
        'tracking': ['跟踪'],
        'trackings': ['跟踪'],
        'tracing': ['跟踪'],
        'tracings': ['跟踪'],
        'monitoring': ['监控'],
        'monitorings': ['监控'],
        'observing': ['观察'],
        'observations': ['观察'],
        'watching': ['观察'],
        'watchings': ['观察'],
        'viewing': ['观察'],
        'viewings': ['观察'],
        'surveying': ['调查'],
        'surveys': ['调查'],
        'studying': ['研究'],
        'studyings': ['研究'],
        'researching': ['研究'],
        'researchings': ['研究'],
        'investigating': ['调查'],
        'investigations': ['调查'],
        'examining': ['检查'],
        'examinations': ['检查'],
        'inspecting': ['检查'],
        'inspections': ['检查'],
        'checking': ['检查'],
        'checkings': ['检查'],
        'testing': ['测试'],
        'testings': ['测试'],
        'trying': ['尝试'],
        'tryings': ['尝试'],
        'attempting': ['尝试'],
        'attempts': ['尝试'],
        'endeavoring': ['努力'],
        'endeavors': ['努力'],
        'striving': ['努力'],
        'strivings': ['努力'],
        'working': ['工作'],
        'workings': ['工作'],
        'laboring': ['工作'],
        'laborings': ['工作'],
        'toiling': ['工作'],
        'toilings': ['工作'],
        'slaving': ['工作'],
        'slavings': ['工作'],
        'drudging': ['工作'],
        'drudgings': ['工作'],
        'grinding': ['研磨'],
        'grindings': ['研磨'],
        'milling': ['碾磨'],
        'millings': ['碾磨'],
        'crushing': ['压碎'],
        'crushings': ['压碎'],
        'pulverizing': ['粉碎'],
        'pulverizations': ['粉碎'],
        'shattering': ['粉碎'],
        'shatterings': ['粉碎'],
        'smashing': ['粉碎'],
        'smashings': ['粉碎'],
        'breaking': ['破碎'],
        'breakings': ['破碎'],
        'fracturing': ['断裂'],
        'fractures': ['断裂'],
        'cracking': ['裂纹'],
        'crackings': ['裂纹'],
        'splitting': ['分裂'],
        'splittings': ['分裂'],
        'dividing': ['分裂'],
        'dividings': ['分裂'],
        'separating': ['分离'],
        'separatings': ['分离'],
        'parting': ['分离'],
        'partings': ['分离'],
        'detaching': ['分离'],
        'detachments': ['分离'],
        'disconnecting': ['断开'],
        'disconnectings': ['断开'],
        'unlinking': ['断开'],
        'unlinkings': ['断开'],
        'untying': ['解开'],
        'untyings': ['解开'],
        'unbinding': ['解开'],
        'unbindings': ['解开'],
        'unfastening': ['解开'],
        'unfastenings': ['解开'],
        'unclasping': ['解开'],
        'unclaspings': ['解开'],
        'unhooking': ['解开'],
        'unhookings': ['解开'],
        'unlatching': ['解开'],
        'unlatchings': ['解开'],
        'unbolting': ['解开'],
        'unboltings': ['解开'],
        'unlocking': ['解锁'],
        'unlockings': ['解锁'],
        'opening': ['打开'],
        'openings': ['打开'],
        'uncovering': ['揭开'],
        'uncoverings': ['揭开'],
        'unveiling': ['揭开'],
        'unveilings': ['揭开'],
        'unmasking': ['揭开'],
        'unmaskings': ['揭开'],
        'unwrapping': ['解开'],
        'unwrappings': ['解开'],
        'unfolding': ['展开'],
        'unfoldings': ['展开'],
        'unrolling': ['展开'],
        'unrollings': ['展开'],
        'unfurling': ['展开'],
        'unfurlings': ['展开'],
        'unraveling': ['解开'],
        'unravelings': ['解开'],
        'untangling': ['解开'],
        'untanglings': ['解开'],
        'unruffling': ['解开'],
        'unrufflings': ['解开'],
        'unscrambling': ['解密'],
        'unscramblings': ['解密'],
        'decoding': ['解码'],
        'decodings': ['解码'],
        'decrypting': ['解密'],
        'decryptions': ['解密'],
        'deciphering': ['破译'],
        'decipherings': ['破译'],
        'interpreting': ['解释'],
        'interpretations': ['解释'],
        'translating': ['翻译'],
        'translations': ['翻译'],
        'rendering': ['渲染'],
        'renderings': ['渲染'],
        'converting': ['转换'],
        'conversions': ['转换'],
        'transforming': ['变换'],
        'transformations': ['变换'],
        'changing': ['改变'],
        'changes': ['改变'],
        'modifying': ['修改'],
        'modifications': ['修改'],
        'altering': ['改变'],
        'alterations': ['改变'],
        'adjusting': ['调整'],
        'adjustments': ['调整'],
        'tuning': ['调整'],
        'tunings': ['调整'],
        'regulating': ['调节'],
        'regulations': ['调节'],
        'controlling': ['控制'],
        'controllings': ['控制'],
        'managing': ['管理'],
        'managements': ['管理'],
        'directing': ['指导'],
        'directions': ['指导'],
        'guiding': ['指导'],
        'guidings': ['指导'],
        'steering': ['引导'],
        'steerings': ['引导'],
        'piloting': ['驾驶'],
        'pilotings': ['驾驶'],
        'navigating': ['导航'],
        'navigations': ['导航'],
        'sailing': ['航行'],
        'sailings': ['航行'],
        'flying': ['飞行'],
        'flyings': ['飞行'],
        'soaring': ['翱翔'],
        'soarings': ['翱翔'],
        'gliding': ['滑翔'],
        'glidings': ['滑翔'],
        'floating': ['漂浮'],
        'floatings': ['漂浮'],
        'drifting': ['漂流'],
        'driftings': ['漂流'],
        'wandering': ['漫游'],
        'wanderings': ['漫游'],
        'roaming': ['漫游'],
        'roamings': ['漫游'],
        'rambling': ['漫游'],
        'ramblings': ['漫游'],
        'strolling': ['漫步'],
        'strollings': ['漫步'],
        'walking': ['散步'],
        'walkings': ['散步'],
        'hiking': ['远足'],
        'hikings': ['远足'],
        'trekking': ['跋涉'],
        'trekkings': ['跋涉'],
        'marching': ['行军'],
        'marchings': ['行军'],
        'parading': ['游行'],
        'paradings': ['游行'],
        'strutting': ['昂首阔步'],
        'struttings': ['昂首阔步'],
        'swaggering': ['昂首阔步'],
        'swaggerings': ['昂首阔步'],
        'striding': ['大步走'],
        'stridings': ['大步走'],
        'stepping': ['踏步'],
        'steppings': ['踏步'],
        'treading': ['踏步'],
        'treadings': ['踏步'],
        'pacing': ['步调'],
        'pacings': ['步调'],
        'measuring': ['测量'],
        'measurings': ['测量'],
        'gauging': ['测量'],
        'gaugings': ['测量'],
        'estimating': ['估算'],
        'estimations': ['估算'],
        'calculating': ['计算'],
        'calculations': ['计算'],
        'computing': ['计算'],
        'computings': ['计算'],
        'figuring': ['计算'],
        'figurings': ['计算'],
        'working': ['计算'],
        'workings': ['计算'],
        'solving': ['求解'],
        'solvings': ['求解'],
        'answering': ['回答'],
        'answers': ['回答'],
        'responding': ['响应'],
        'responses': ['响应'],
        'reacting': ['反应'],
        'reactions': ['反应'],
        'acting': ['行动'],
        'actings': ['行动'],
        'performing': ['执行'],
        'performances': ['执行'],
        'doing': ['做'],
        'doings': ['做'],
        'making': ['制造'],
        'makings': ['制造'],
        'creating': ['创造'],
        'creations': ['创造'],
        'building': ['构建'],
        'buildings': ['构建'],
        'constructing': ['建造'],
        'constructions': ['建造'],
        'forming': ['形成'],
        'formings': ['形成'],
        'shaping': ['塑造'],
        'shapings': ['塑造'],
        'molding': ['塑造'],
        'moldings': ['塑造'],
        'modeling': ['建模'],
        'modelings': ['建模'],
        'simulating': ['模拟'],
        'simulations': ['模拟'],
        'imitating': ['模仿'],
        'imitations': ['模仿'],
        'copying': ['复制'],
        'copyings': ['复制'],
        'duplicating': ['复制'],
        'duplications': ['复制'],
        'replicating': ['复制'],
        'replications': ['复制'],
        'reproducing': ['复制'],
        'reproductions': ['复制'],
        'cloning': ['克隆'],
        'clonings': ['克隆'],
        'mirroring': ['镜像'],
        'mirrorings': ['镜像'],
        'reflecting': ['反射'],
        'reflections': ['反射'],
        'bouncing': ['弹跳'],
        'bouncings': ['弹跳'],
        'rebounding': ['弹回'],
        'reboundings': ['弹回'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'recovering': ['恢复'],
        'recoverings': ['恢复'],
        'restoring': ['恢复'],
        'restorations': ['恢复'],
        'rebuilding': ['重建'],
        'rebuildings': ['重建'],
        'reconstructing': ['重建'],
        'reconstructions': ['重建'],
        'recreating': ['重建'],
        'recreations': ['重建'],
        'renewing': ['更新'],
        'renewals': ['更新'],
        'refreshing': ['刷新'],
        'refreshings': ['刷新'],
        'reviving': ['恢复'],
        'revivals': ['恢复'],
        'resurrecting': ['复活'],
        'resurrections': ['复活'],
        'awakening': ['唤醒'],
        'awakenings': ['唤醒'],
        'arousing': ['唤醒'],
        'arousings': ['唤醒'],
        'stimulating': ['刺激'],
        'stimulations': ['刺激'],
        'exciting': ['激发'],
        'excitings': ['激发'],
        'thrilling': ['兴奋'],
        'thrillings': ['兴奋'],
        'electrifying': ['兴奋'],
        'electrifications': ['兴奋'],
        'inspiring': ['启发'],
        'inspirations': ['启发'],
        'motivating': ['激励'],
        'motivations': ['激励'],
        'encouraging': ['鼓励'],
        'encouragements': ['鼓励'],
        'heartening': ['鼓舞'],
        'heartenings': ['鼓舞'],
        'cheering': ['欢呼'],
        'cheerings': ['欢呼'],
        'uplifting': ['提升'],
        'upliftings': ['提升'],
        'elevating': ['提升'],
        'elevations': ['提升'],
        'raising': ['提高'],
        'raisings': ['提高'],
        'lifting': ['举起'],
        'liftings': ['举起'],
        'hoisting': ['举起'],
        'hoistings': ['举起'],
        'boosting': ['提高'],
        'boostings': ['提高'],
        'enhancing': ['增强'],
        'enhancements': ['增强'],
        'improving': ['改进'],
        'improvements': ['改进'],
        'bettering': ['改善'],
        'betterings': ['改善'],
        'amending': ['修正'],
        'amendings': ['修正'],
        'correcting': ['纠正'],
        'corrections': ['纠正'],
        'fixing': ['修复'],
        'fixings': ['修复'],
        'repairing': ['修复'],
        'repairings': ['修复'],
        'mending': ['修复'],
        'mendings': ['修复'],
        'patching': ['修补'],
        'patchings': ['修补'],
        'darning': ['修补'],
        'darnings': ['修补'],
        'stitching': ['缝合'],
        'stitchings': ['缝合'],
        'sewing': ['缝制'],
        'sewings': ['缝制'],
        'knitting': ['编织'],
        'knittings': ['编织'],
        'weaving': ['编织'],
        'weavings': ['编织'],
        'spinning': ['纺纱'],
        'spinnings': ['纺纱'],
        'twisting': ['扭曲'],
        'twistings': ['扭曲'],
        'turning': ['转动'],
        'turnings': ['转动'],
        'rotating': ['旋转'],
        'rotations': ['旋转'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'circling': ['旋转'],
        'circlings': ['旋转'],
        'orbiting': ['轨道'],
        'orbitings': ['轨道'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'gyrating': ['旋转'],
        'gyrations': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'edying': ['旋转'],
        'edyings': ['旋转'],
        'vortexing': ['旋转'],
        'vortexings': ['旋转'],
        'swirling': ['旋转'],
        'swirlings': ['旋转'],
        'whirling': ['旋转'],
        'whirlings': ['旋转'],
        'twirling': ['旋转'],
        'twirlings': ['旋转'],
        'spinning': ['旋转'],
        'spinnings': ['旋转'],
        'rotating': ['旋转'],
        'rotations': ['旋转'],
        'revolving': ['旋转'],
        'revolvings': ['旋转'],
        'gyrating': ['旋转'],
        'gyrations': ['旋转'],
        'cycling': ['循环'],
        'cyclings': ['循环'],
        'looping': ['循环'],
        'loopings': ['循环'],
        'iterating': ['迭代'],
        'iterations': ['迭代'],
        'repeating': ['重复'],
        'repeatings': ['重复'],
        'recurring': ['重复'],
        'recurrings': ['重复'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'restoring': ['恢复'],
        'restorations': ['恢复'],
        'recovering': ['恢复'],
        'recoverings': ['恢复'],
        'retrieving': ['检索'],
        'retrievals': ['检索'],
        'fetching': ['获取'],
        'fetchings': ['获取'],
        'obtaining': ['获取'],
        'obtainings': ['获取'],
        'acquiring': ['获取'],
        'acquisitions': ['获取'],
        'procuring': ['获取'],
        'procurings': ['获取'],
        'securing': ['获取'],
        'securings': ['获取'],
        'gaining': ['获取'],
        'gainings': ['获取'],
        'earning': ['获得'],
        'earnings': ['获得'],
        'making': ['获得'],
        'makings': ['获得'],
        'winning': ['赢得'],
        'winnings': ['赢得'],
        'achieving': ['实现'],
        'achievements': ['实现'],
        'accomplishing': ['实现'],
        'accomplishments': ['实现'],
        'fulfilling': ['实现'],
        'fulfillments': ['实现'],
        'realizing': ['实现'],
        'realizations': ['实现'],
        'actualizing': ['实现'],
        'actualizations': ['实现'],
        'materializing': ['实现'],
        'materializations': ['实现'],
        'manifesting': ['表现'],
        'manifestations': ['表现'],
        'displaying': ['显示'],
        'displayings': ['显示'],
        'showing': ['显示'],
        'showings': ['显示'],
        'demonstrating': ['证明'],
        'demonstrations': ['证明'],
        'proving': ['证明'],
        'provings': ['证明'],
        'establishing': ['确立'],
        'establishments': ['确立'],
        'setting': ['设置'],
        'settings': ['设置'],
        'determining': ['确定'],
        'determinations': ['确定'],
        'fixing': ['确定'],
        'fixings': ['确定'],
        'settling': ['解决'],
        'settlings': ['解决'],
        'resolving': ['解决'],
        'resolutions': ['解决'],
        'solving': ['解决'],
        'solutions': ['解决'],
        'answering': ['回答'],
        'answers': ['回答'],
        'responding': ['回应'],
        'responses': ['回应'],
        'replying': ['回答'],
        'replies': ['回答'],
        'returning': ['返回'],
        'returns': ['返回'],
        'reverting': ['恢复'],
        'revertings': ['恢复'],
        'going': ['去'],
        'goings': ['去'],
        'leaving': ['离开'],
        'leavings': ['离开'],
        'departing': ['离开'],
        'departings': ['离开'],
        'exiting': ['退出'],
        'exits': ['退出'],
        'withdrawing': ['退出'],
        'withdrawings': ['退出'],
        'retiring': ['退休'],
        'retirements': ['退休'],
        'stepping': ['退出'],
        'steppings': ['退出'],
        'resigning': ['辞职'],
        'resignings': ['辞职'],
        'quitting': ['退出'],
        'quittings': ['退出'],
        'abandoning': ['放弃'],
        'abandonments': ['放弃'],
        'deserting': ['放弃'],
        'desertions': ['放弃'],
        'forsaking': ['放弃'],
        'forsakings': ['放弃'],
        'renouncing': ['放弃'],
        'renunciations': ['放弃'],
        'relinquishing': ['放弃'],
        'relinquishments': ['放弃'],
        # 化学领域
        'chemistry': ['化学'],
        'organic': ['有机', '有机化学'],
        'inorganic': ['无机', '无机化学'],
        'biochemistry': ['生物化学'],
        'polymer': ['高分子', '高分子化学'],
        'electrochemistry': ['电化学'],
        'kinetics': ['动力学', '化学动力学'],
        'physical_chem': ['物理化学'],
        'analytical_chem': ['分析化学'],
        'medicinal': ['药物化学'],
        'materials_chem': ['材料化学'],
        # 生物领域
        'biology': ['生物', '生物学'],
        'cell': ['细胞', '细胞学'],
        'molecular': ['分子', '分子生物学'],
        'genetics': ['遗传', '遗传学'],
        'ecology': ['生态', '生态学'],
        'evolution': ['进化', '进化论'],
        'physiology': ['生理学'],
        'microbiology': ['微生物'],
        'immunology': ['免疫学'],
        'neuroscience': ['神经科学'],
        'biophysics': ['生物物理'],
        'bioinformatics': ['生物信息学'],
        # 生物/化学/分子模拟领域
        'simulation': ['模拟', '分子模拟'],
        'computation': ['计算'],
        'modeling': ['建模'],
        # 物理/化学通用
        'physical': ['物理', '物理化学'],
        'reaction': ['反应', '化学反应'],
        'mechanism': ['机理'],
        'principle': ['原理'],
        'chemical': ['化学'],
        # 生物领域
        'biology': ['生物', '生物学'],
        'cell': ['细胞', '细胞学'],
        'molecular': ['分子', '分子生物学'],
        'genetics': ['遗传', '遗传学'],
        'ecology': ['生态', '生态学'],
        'evolution': ['进化', '进化论'],
        'physiology': ['生理学'],
    }
    
    # 中文到英文的反向映射
    CHINESE_TO_ENGLISH = {}
    for _eng, _chns in DOMAIN_KEYWORDS_FULL.items():
        for _ch in _chns:
            if _ch not in CHINESE_TO_ENGLISH:
                CHINESE_TO_ENGLISH[_ch] = []
            if _eng not in CHINESE_TO_ENGLISH[_ch]:
                CHINESE_TO_ENGLISH[_ch].append(_eng)
    
    # 额外中文专业词汇到领域的直接映射
    CHINESE_DOMAIN_DIRECT = {
        '数论': ['number', 'analytic', 'algebraic'],
        '抽象代数': ['algebra'],
        '线性代数': ['linear', 'algebra'],
        '高等代数': ['algebra', 'linear'],
        '矩阵论': ['matrix'],
        '模论': ['module'],
        '群论': ['group'],
        '环论': ['ring'],
        '域论': ['field'],
        '伽罗瓦理论': ['galois'],
        '表示论': ['representation'],
        '李代数': ['lie'],
        '李群': ['lie'],
        '交换代数': ['commutative', 'algebra'],
        '同调代数': ['homology', 'cohomology', 'algebra'],
        '范畴论': ['category', 'functor'],
        '张量': ['tensor'],
        '特征值': ['characteristic', 'eigenvalue'],
        '特征向量': ['eigenvector'],
        '行列式': ['determinant'],
        '多项式': ['polynomial'],
        '理想': ['ideal'],
        '布尔代数': ['boolean'],
        '微分几何': ['differential', 'geometry'],
        '黎曼几何': ['riemann', 'riemannian'],
        '拓扑学': ['topology'],
        '代数拓扑': ['topology', 'homotopy', 'homology', 'cohomology'],
        '同伦论': ['homotopy'],
        '同调论': ['homology'],
        '上同调论': ['cohomology'],
        '层论': ['sheaf'],
        '纤维丛': ['bundle', 'fibration'],
        '射影几何': ['projective'],
        '仿射几何': ['affine'],
        '复几何': ['complex'],
        '辛几何': ['symplectic'],
        '代数几何': ['algebraic', 'geometry', 'scheme'],
        '解析几何': ['geometry', 'analytic'],
        '数学分析': ['analysis', 'calculus'],
        '实变函数': ['real', 'analysis'],
        '复变函数': ['complex', 'analysis'],
        '泛函分析': ['functional', 'analysis'],
        '测度论': ['measure'],
        '积分方程': ['integral'],
        '常微分方程': ['ode', 'differential'],
        '偏微分方程': ['pde', 'differential'],
        '积分': ['integral', 'calculus'],
        '微分': ['differential', 'calculus'],
        '导数': ['derivative'],
        '极限': ['limit'],
        '级数': ['series'],
        '收敛': ['convergence'],
        '发散': ['divergence'],
        '傅里叶分析': ['fourier'],
        '调和分析': ['harmony', 'fourier'],
        '小波分析': ['wavelet'],
        '算子理论': ['operator'],
        '谱理论': ['spectral'],
        '广义函数': ['distribution'],
        '变分法': ['variational'],
        '最优化': ['optimization'],
        '经典力学': ['classical', 'mechanics', 'newtonian'],
        '牛顿力学': ['newtonian', 'mechanics'],
        '拉格朗日力学': ['lagrangian', 'mechanics'],
        '哈密顿力学': ['hamiltonian', 'mechanics'],
        '量子力学': ['quantum'],
        '量子场论': ['quantum', 'field'],
        '统计力学': ['statistical', 'mechanics'],
        '电动力学': ['electrodynamics'],
        '热力学': ['thermodynamics'],
        '统计物理': ['statistical', 'physics'],
        '相对论': ['relativity'],
        '宇宙学': ['cosmology'],
        '天体物理': ['astrophysics'],
        '弦论': ['string'],
        '粒子物理': ['particle'],
        '凝聚态物理': ['condensed'],
        '固体物理': ['solid'],
        '光学': ['optics'],
        '声学': ['acoustics'],
        '电磁学': ['electromagnetism'],
        '算法': ['algorithm'],
        '数据结构': ['data', 'structure'],
        '程序设计': ['programming'],
        '人工智能': ['artificial', 'intelligence'],
        '机器学习': ['machine', 'learning'],
        '深度学习': ['deep', 'learning'],
        '神经网络': ['neural', 'network'],
        '计算机视觉': ['vision', 'computer'],
        '自然语言处理': ['nlp'],
        '数据库': ['database'],
        '计算机网络': ['network', 'computer'],
        '网络安全': ['security', 'network'],
        '密码学': ['cryptography'],
        '分布式系统': ['distributed'],
        '并行计算': ['parallel'],
        '云计算': ['cloud'],
        '操作系统': ['operating'],
        '编译原理': ['compiler'],
        '软件工程': ['software'],
        '计算机图形学': ['graphics'],
        '机器人学': ['robotics'],
        '有机化学': ['organic', 'chemistry'],
        '无机化学': ['inorganic', 'chemistry'],
        '物理化学': ['physical', 'chemistry'],
        '分析化学': ['analytical', 'chemistry'],
        '生物化学': ['biochemistry'],
        '光谱学': ['spectroscopy'],
        '电化学': ['electrochemistry'],
        '化学动力学': ['kinetics'],
        '高分子化学': ['polymer'],
        '细胞学': ['cell'],
        '分子生物学': ['molecular', 'biology'],
        '遗传学': ['genetics'],
        '生态学': ['ecology'],
        '微生物学': ['microbiology'],
        '神经科学': ['neuroscience'],
        '进化论': ['evolution'],
        '生理学': ['physiology'],
        '概率论': ['probability'],
        '统计学': ['statistics'],
        '随机过程': ['stochastic'],
        '数值分析': ['numerical'],
        '数值计算': ['numerical'],
        '组合数学': ['combinatorics'],
        '图论': ['graph'],
        '运筹学': ['operations', 'optimization'],
        '定理': ['theorem'],
        '引理': ['lemma'],
        '推论': ['corollary'],
        '证明': ['proof'],
        '公理': ['axiom'],
        '不变量': ['invariant'],
        '对称性': ['symmetry'],
        '对偶性': ['duality'],
        '连续性': ['continuous', 'continuity'],
        '可微性': ['differentiable'],
        '可积性': ['integrable'],
        '和声学': ['harmony'],
        '对位法': ['counterpoint'],
        '乐理': ['theory'],
        '音乐理论': ['theory', 'music'],
        '作曲理论': ['composer', 'theory'],
        '交响乐': ['symphony'],
        '管弦乐': ['orchestra'],
        '室内乐': ['chamber'],
        '声乐': ['vocal'],
        '器乐': ['instrument'],
        '歌剧': ['opera'],
    }
    
    # 合并到 CHINESE_TO_ENGLISH
    for _ch, _engs in CHINESE_DOMAIN_DIRECT.items():
        if _ch not in CHINESE_TO_ENGLISH:
            CHINESE_TO_ENGLISH[_ch] = []
        for _e in _engs:
            if _e not in CHINESE_TO_ENGLISH[_ch]:
                CHINESE_TO_ENGLISH[_ch].append(_e)
    
    STOPWORDS = {
        'the', 'and', 'for', 'with', 'from', 'into', 'about', 'against', 'between',
        'through', 'during', 'before', 'after', 'above', 'below', 'to', 'of', 'in',
        'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
        'most', 'other', 'some', 'such', 'only', 'own', 'same', 'so', 'than',
        'too', 'very', 'can', 'will', 'just', 'should', 'now', 'also', 'but',
        'not', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was',
        'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do',
        'does', 'did', 'doing', 'would', 'could', 'may', 'might', 'must',
        '课程', '课时', '系统', '理论', '基础', '原理', '导论', '应用', '实践',
        '实验', '设计', '方法', '概论', '入门', '教材', '习题', '解答', '答案',
        '详解', '教程', '指南', '译丛', '精品', '第一', '第二', '第三', '第四',
        '第五', '第六', '第七', '第八', '第九', '第十', '上册', '下册', '上卷',
        '下卷', '第1版', '第2版', '第3版', '章节', '内容', '版本',
        '资料', '讲义', '总复习', '测试', '考试', '复习', '提纲', '大纲',
        '笔记', '总结', '要点', '重点', '难点', '考点', '知识点', '知识',
        '概述', '简介', '总论', '绪论', '引言', '前言', '序言', '后记',
        '目录', '索引', '参考文献', '附录', '图表', '插图', '公式',
        '问题', '思考', '讨论', '研究', '分析', '说明', '讲解', '论述',
        '第', '章', '节', '篇', '卷', '册', '部', '集', '期', '号',
        '基于', '关于', '对于', '由于', '通过', '利用', '采用', '使用',
        '实现', '完成', '提出', '给出', '建立', '构建', '形成', '得到',
        '进行', '开展', '实施', '提供', '达到', '获得', '表明', '证明',
        '探讨', '讨论', '研究', '分析', '总结', '归纳', '概括', '论述',
        '阐述', '说明', '介绍', '描述', '论证', '推理',
        '推导', '演算', '计算', '求解', '优化', '改进', '完善',
        '提高', '增强', '扩展', '推广', '发展', '突破',
        'pdf', 'doc', 'docx', 'zip', 'rar', 'epub', 'introduction', 'basic',
        'advanced', 'problems', 'solutions', 'manual', 'guide', 'edition',
        'version', 'vol', 'master', 'main', 'chapter', 'part', 'section',
        'zlibrary', 'library', 'ebook', 'book', 'textbook', 'notes',
        '简体中文', '繁体中文', '中文版', '英文版', '原版', '影印版',
        '修订版', '增补版', '新版', '旧版', '全套', '合集', '全集',
        '2020', '2021', '2022', '2023', '2024', '2025', '2026',
    }

    def _extract_keywords(self, name: str) -> List[str]:
        """从文件名/标题提取关键词（jieba分词 + 停用词过滤 + 中英文）"""
        cleaned = re.sub(r'^[\d_\-\.]+', '', name)
        cleaned = re.sub(r'[\s_\-—]+', ' ', cleaned).strip()
        
        keywords = []
        
        # 1. jieba 分词（中文）
        try:
            import jieba
            for w in jieba.cut(cleaned):
                w = w.strip()
                if len(w) >= 2 and w not in self.STOPWORDS:
                    keywords.append(w.lower())
        except ImportError:
            # 无 jieba 时回退到正则分词
            cn_words = re.findall(r'[\u4e00-\u9fff]{2,}', cleaned)
            keywords.extend(w.lower() for w in cn_words if w not in self.STOPWORDS)
        
        # 2. 提取英文词汇（3字母以上）
        en_words = re.findall(r'[a-zA-Z]{3,}', cleaned)
        keywords.extend(w.lower() for w in en_words if w.lower() not in self.STOPWORDS)
        
        # 去重
        return list(dict.fromkeys(keywords))[:30]

    def _build_domain_match_index(self):
        """构建领域词典的倒排索引，用于快速匹配"""
        if hasattr(self, '_domain_match_index'):
            return self._domain_match_index
        
        index = {}
        for eng_kw, ch_translations in self.DOMAIN_KEYWORDS_FULL.items():
            for ch in ch_translations:
                # 完整词
                idx_key = ch.lower()
                if idx_key not in index:
                    index[idx_key] = set()
                index[idx_key].add(eng_kw)
                
                # 2字窗口子串（破解复合词）
                if len(ch) >= 4:
                    for i in range(len(ch) - 1):
                        sub = ch[i:i+2]
                        sub_key = sub.lower()
                        if sub_key not in index:
                            index[sub_key] = set()
                        index[sub_key].add(eng_kw)
                
                # 单字级别（2字以上词中的每个字）
                for char in ch:
                    char_key = char.lower()
                    if char_key not in index:
                        index[char_key] = set()
                    index[char_key].add(eng_kw)
        
        self._domain_match_index = index
        return index

    def _compute_domain_match_score(self, filename_keywords: List[str], course_title: str, 
                                     course_title_keywords: List[str], course: Optional[Dict] = None) -> tuple:
        """
        基于领域词典倒排索引 + jieba分词 的超弱匹配
        返回 (matched_count, matched_domains_set)
        
        核心策略：宁可错配也不能少配
        关键机制：倒排索引将中文子串映射到英文领域词，解决复合词拆分问题
        增强：支持课程的 sections/lessons 标题匹配
        """
        matched_count = 0
        matched_domains = set()
        domain_index = self._build_domain_match_index()
        file_kw_set = set(filename_keywords)
        
        # 收集课程的所有文本（标题 + sections + lessons）
        all_course_texts = [course_title]
        all_course_kw_sets = set()
        all_course_kw_sets.add(frozenset(course_title_keywords))
        if course:
            for sec in course.get("sections", []):
                st = sec.get("section_title", "")
                if st:
                    all_course_texts.append(st)
                    all_course_kw_sets.add(frozenset(self._extract_keywords(st)))
            for lesson in course.get("lessons", []):
                lt = lesson.get("lesson_title", "")
                if lt:
                    all_course_texts.append(lt)
                    all_course_kw_sets.add(frozenset(self._extract_keywords(lt)))
        
        # 正向：文件名关键词 → 领域词典/倒排索引 → 课程标题/sections/lessons
        for kw in filename_keywords:
            # 1. 直接匹配课程标题关键词
            if kw in course_title_keywords:
                matched_count += 1
                matched_domains.add(kw)
                continue
            
            # 2. 文件名英文关键词在领域词典中 → 中文翻译 → 子串匹配（全文本）
            if kw in self.DOMAIN_KEYWORDS_FULL:
                related_ch = self.DOMAIN_KEYWORDS_FULL[kw]
                for ch in related_ch:
                    # 检查所有课程文本
                    for ct in all_course_texts:
                        if ch in ct:
                            matched_count += 1
                            matched_domains.add(kw)
                            break
                    if kw in matched_domains:
                        break
                    
                    # 检查所有课程关键词集
                    for ckws in all_course_kw_sets:
                        if any(ch in ct for ct in ckws):
                            matched_count += 1
                            matched_domains.add(kw)
                            break
                    if kw in matched_domains:
                        break
                    
                    # 复合词拆成2字窗口
                    if len(ch) >= 4:
                        windows = [ch[i:i+2] for i in range(len(ch)-1)]
                        for w in windows:
                            for ct in all_course_texts:
                                if w in ct:
                                    matched_count += 1
                                    matched_domains.add(kw)
                                    break
                            if kw in matched_domains:
                                break
                            for ckws in all_course_kw_sets:
                                if any(w in ct for ct in ckws):
                                    matched_count += 1
                                    matched_domains.add(kw)
                                    break
                            if kw in matched_domains:
                                break
            
            # 3. 文件名中文关键词（不在词典的复合词）→ 拆成2字窗口 → 倒排索引反向查找
            if all('\u4e00' <= c <= '\u9fff' for c in kw) and len(kw) >= 3:
                for i in range(len(kw) - 1):
                    sub = kw[i:i+2]
                    if sub in domain_index:
                        for eng_kw in domain_index[sub]:
                            if eng_kw not in matched_domains:
                                matched_count += 1
                                matched_domains.add(eng_kw)
            
            # 4. 文件名中文关键词 → 倒排索引直接查找（单字/双字）
            if kw in domain_index:
                for eng_kw in domain_index[kw]:
                    if eng_kw not in matched_domains:
                        matched_count += 1
                        matched_domains.add(eng_kw)
            
            # 5. 文件名中文关键词 → 反向英文映射
            if kw in self.CHINESE_TO_ENGLISH:
                related_eng = self.CHINESE_TO_ENGLISH[kw]
                for eng in related_eng:
                    if eng not in matched_domains:
                        matched_count += 1
                        matched_domains.add(kw)
                        break
        
        # 反向：课程标题关键词 → 倒排索引 → 英文领域词 → 检查文件名
        all_kw_set = set()
        for ckws in all_course_kw_sets:
            all_kw_set.update(ckws)
        
        for kw in all_kw_set:
            if kw in file_kw_set:
                matched_count += 1
                matched_domains.add(kw)
                continue
            
            # 通过倒排索引：课程标题的中文词 → 英文领域词 → 文件名
            if kw in domain_index:
                related_eng = domain_index[kw]
                for eng in related_eng:
                    if eng in file_kw_set:
                        matched_count += 1
                        matched_domains.add(eng)
                        break
            
            # 领域词典：课程标题词在中文翻译中 → 英文领域词 → 文件名
            for eng, chns in self.DOMAIN_KEYWORDS_FULL.items():
                if kw in chns or kw == eng:
                    if eng in file_kw_set:
                        matched_count += 1
                        matched_domains.add(eng)
                        break
        
        return matched_count, matched_domains

    def _match_resource_to_course(self, resource: Dict, course: Dict) -> float:
        """
        计算资源与课程的匹配分数
        
        策略：超弱多匹配 + 中英文字典对照翻译
        核心原则：宁可错配也不能少配
        """
        score = 0.0
        filename = resource.get("filename", "")
        stem = resource.get("stem", "")
        
        course_title = course.get("course_title", "")
        
        # 1. 课程标题直接匹配（高权重）
        course_title_clean = re.sub(r'[\s_\-—（(].*?[）)]', '', course_title.lower())
        if course_title_clean and course_title_clean in filename.lower():
            score += 3.0
        if course_title_clean and course_title_clean in stem.lower():
            score += 2.0
        
        # 2. 课时标题匹配
        for lesson in course.get("lessons", []):
            lt = lesson.get("lesson_title", "").lower()
            if lt and lt in filename.lower():
                score += 1.5
                break
        
        # 3. Section 标题匹配
        for sec in course.get("sections", []):
            st = sec.get("section_title", "").lower()
            if st and st in filename.lower():
                score += 0.8
        
        # 4. 学科域匹配
        domain = course.get("domain", "")
        if domain:
            domain_name = DOMAIN_KEYWORDS.get(domain, {}).get("name", "").lower()
            if domain_name and domain_name in filename.lower():
                score += 1.5
            # 也检查中文域名
            domain_cn = DOMAIN_KEYWORDS.get(domain, {}).get("name_cn", "")
            if domain_cn and domain_cn in filename:
                score += 1.5
        
        # 5. 超弱领域词典匹配 + 中英文双向翻译
        file_keywords = self._extract_keywords(stem or filename)
        course_keywords = self._extract_keywords(course_title)
        
        matched_count, matched_domains = self._compute_domain_match_score(
            file_keywords, course_title, course_keywords, course
        )
        
        # 只要有领域词匹配就加分（超弱策略）
        if matched_domains:
            score += min(0.3 + len(matched_domains) * 0.25 + matched_count * 0.1, 2.0)
        
        # 6. 关键词模糊匹配
        keywords = resource.get("extracted_metadata", {}).get("keywords", [])
        for kw in keywords:
            if kw.lower() in course_title.lower():
                score += 0.3
        
        # 7. 标签匹配
        for tag in resource.get("tags", []):
            if tag.startswith("content:") and tag.split(":")[1] in course_title.lower():
                score += 0.2
        
        # 8. 极弱匹配兜底：只要文件名有非停用词出现在课程标题中，就给基础分
        if file_keywords and course_keywords:
            common = set(file_keywords) & set(course_keywords)
            if common:
                score += 0.2 * len(common)
        
        return score

    def _generate_tags(self, name: str, ext: str) -> List[str]:
        """生成智能分类标签"""
        tags = []
        
        # 资源类型标签
        res_type = self.FILE_TYPE_MAP.get(ext, "other")
        tags.append(f"type:{res_type}")
        
        # 内容推断标签
        name_lower = name.lower()
        if any(kw in name_lower for kw in ['syllabus', '课程大纲', '教学大纲']):
            tags.append("content:syllabus")
        elif any(kw in name_lower for kw in ['讲义', 'lecture', 'lecture note']):
            tags.append("content:lecture_notes")
        elif any(kw in name_lower for kw in ['习题', 'homework', 'exercise', 'problem', '作业']):
            tags.append("content:homework")
        elif any(kw in name_lower for kw in ['解答', 'solution', '答案', 'answer']):
            tags.append("content:solution")
        elif any(kw in name_lower for kw in ['实验', 'lab', 'experiment']):
            tags.append("content:lab")
        elif any(kw in name_lower for kw in ['代码', 'code', 'script', '实现']):
            tags.append("content:code")
        elif any(kw in name_lower for kw in ['数据', 'data', 'dataset']):
            tags.append("content:data")
        elif any(kw in name_lower for kw in ['参考', 'reference', '文献']):
            tags.append("content:reference")
        
        return tags

    def match_to_courses(self, resources: List[Dict], courses: List[Dict],
                         threshold: float = 0.05) -> Dict[str, List[Dict]]:
        """
        将资源分配到课程
        
        策略：超弱多匹配 + 手动多匹配机制
        核心原则：宁可错配也不能少配 — 只要有一丝关联就分配
        
        Args:
            resources: 扫描到的资源列表
            courses: 课程列表（含 title, keywords 等）
            threshold: 匹配阈值（极低，默认 0.05）
        
        Returns:
            {course_id: [resource, ...]}
        """
        self.course_mapping = {c.get("note_id", c.get("course_title", "")): [] for c in courses}
        
        # 预计算所有课程的关键词（避免重复计算）
        course_keywords_cache = {}
        for c in courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            course_keywords_cache[cid] = self._extract_keywords(title)
        
        for res in resources:
            scores = []
            for c in courses:
                cid = c.get("note_id", c.get("course_title", ""))
                score = self._match_resource_to_course(res, c)
                # 超弱阈值：只要 > 0 就纳入候选
                if score >= threshold:
                    scores.append((c, score, cid))
            
            scores.sort(key=lambda x: x[1], reverse=True)
            
            # 超弱多匹配：只要分数 > 0 就全部纳入（不限制数量）
            # 让用户在对话框中手动调整
            for course, score, cid in scores:
                res_copy = dict(res)
                res_copy["match_score"] = score
                res_copy["matched_courses"].append({
                    "course_id": cid,
                    "course_title": course.get("course_title", ""),
                    "score": score
                })
                self.course_mapping[cid].append(res_copy)
        
        return self.course_mapping

    def generate_import_report(self) -> Dict:
        """生成导入建议报告"""
        report = {
            "total_resources": len(self.resources),
            "by_type": {},
            "by_course": {},
            "unmatched": [],
            "suggestions": [],
        }
        
        # 按类型统计
        for res in self.resources:
            rtype = res.get("resource_type", "other")
            report["by_type"][rtype] = report["by_type"].get(rtype, 0) + 1
        
        # 按课程统计
        for cid, resources in self.course_mapping.items():
            if resources:
                report["by_course"][cid] = {
                    "count": len(resources),
                    "resources": [{"filename": r["filename"], "type": r["resource_type"], "score": r.get("match_score", 0)}
                                  for r in resources]
                }
        
        # 未匹配资源
        for res in self.resources:
            if not res.get("matched_courses"):
                report["unmatched"].append({
                    "filename": res["filename"],
                    "type": res["resource_type"],
                    "path": res["relative_path"]
                })
        
        # 生成建议
        if report["unmatched"]:
            report["suggestions"].append(
                f"发现 {len(report['unmatched'])} 个未匹配资源，建议检查文件名是否包含课程关键词"
            )
        
        empty_courses = [cid for cid, res in self.course_mapping.items() if not res]
        if empty_courses:
            report["suggestions"].append(
                f"以下课程没有匹配到资源: {', '.join(empty_courses[:5])}"
            )
        
        return report
