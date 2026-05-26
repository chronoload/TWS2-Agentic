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
import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime

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
