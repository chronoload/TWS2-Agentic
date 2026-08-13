"""从 CourseTracker 课程数据 + Notes/*.Rmd 笔记文件解析初始概念。

三阶段幂等同步：
  1. 课程 JSON → 课程/课时概念 → 按领域入线程
  2. 未被课程匹配的笔记 → 独立笔记概念 → 按目录名入线程
  3. 笔记正文 → jieba 分词 → 新术语概念 → 入同一线程
"""

import json
import re
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import EcosystemState, Concept, SourceRef, ResearchThread

logger = logging.getLogger(__name__)

# ── 约定路径 ──

COURSES_JSON = "courses_structured.json"
NOTES_DIR = "Notes"


def _read_courses_json(workspace_dir: str) -> List[dict]:
    """读取 CourseTracker 课程 JSON"""
    path = Path(workspace_dir) / COURSES_JSON
    if not path.exists():
        logger.warning(f"coursetracker JSON not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        courses = data.get("courses", [])
        logger.info(f"Loaded {len(courses)} courses from {path.name}")
        return courses
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
        return []


def _scan_notes(workspace_dir: str) -> List[Tuple[str, str, str]]:
    """扫描 Notes/ 下所有 .Rmd 文件，返回 (课程目录名, 文件名, 完整路径)"""
    notes_base = Path(workspace_dir) / NOTES_DIR
    if not notes_base.exists():
        logger.warning(f"Notes dir not found: {notes_base}")
        return []
    results: List[Tuple[str, str, str]] = []
    for course_dir in sorted(notes_base.iterdir()):
        if not course_dir.is_dir() or course_dir.name.startswith("."):
            continue
        for f in sorted(course_dir.glob("*.Rmd")):
            results.append((course_dir.name, f.name, str(f)))
    logger.info(f"Scanned {len(results)} .Rmd files in Notes/")
    return results


def _parse_lesson_number(filename: str) -> Optional[int]:
    """从笔记文件名解析课时号：L{数字} 或 L{数字}_{主题}.Rmd"""
    m = re.search(r"L(\d+)", filename)
    return int(m.group(1)) if m else None


def _find_lesson(courses: List[dict], lesson_number: int) -> Optional[Tuple[dict, dict]]:
    """根据 lesson_number 查找 (course, lesson) 对"""
    for course in courses:
        for lesson in course.get("lessons", []):
            if lesson.get("lesson_number") == lesson_number:
                return course, lesson
    return None


def _slugify(label: str) -> str:
    """简单 slug，用于 id 生成"""
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", label).strip("_")
    return s[:48]


def _concept_id(label: str, prefix: str = "") -> str:
    base = _slugify(label) or uuid.uuid4().hex[:8]
    return f"{prefix}_{base}"[:32] if prefix else base[:24]


# ── 域 → 线程映射 ──

DOMAIN_NAMES = {
    "A": "代数学域", "D": "离散结构域", "P": "系统物理域",
    "C": "范畴论域", "M": "建模与计算域", "S": "合成生信域",
    "N": "分析学域", "CS": "计算机系统域", "SE": "软件工程域",
    "DS": "数据结构与算法域", "DE": "数字电路与嵌入式域",
    "LM": "逻辑与数学基础域", "BIO": "生物信息域", "UNKNOWN": "未知域",
}

_era_prefix_order = ["LM", "A", "N", "C", "M", "P", "D", "DS", "CS", "SE", "DE", "S", "BIO"]


# ── 笔记正文清洗 ──


def _strip_rmd_body(filepath: str) -> str:
    """读取 .Rmd 文件，去掉 YAML front matter 和代码块，返回纯文本"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    content = re.sub(r"```[\s\S]*?```", "", content)
    content = re.sub(r"\$\$[\s\S]*?\$\$", "", content)
    content = re.sub(r"\$[^\$]*?\$", "", content)
    content = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", content)
    content = re.sub(r"<[^>]+>", "", content)
    content = re.sub(r"^#+\s*", "", content, flags=re.MULTILINE)
    return content.strip()


# ── 标题关键词 → 领域映射 ──

_DOMAIN_KEYWORDS: List[Tuple[str, str]] = [
    # 顺序重要：更具体的匹配在前
    ("数据结构与算法", "DS"),
    ("算法", "DS"),                      # 数据结构与算法域
    ("数字电路.*嵌入式", "DE"),
    ("数字电路", "DE"),
    ("嵌入式", "DE"),                    # 数字电路与嵌入式域
    ("操作系统.*计算机.*体系结构", "CS"),
    ("操作系统", "CS"),
    ("计算机体系结构", "CS"),
    ("计算机系统", "CS"),                # 计算机系统域
    ("软件工程.*系统设计", "SE"),
    ("软件工程", "SE"),
    ("软件.*实时.*优化", "SE"),          # 软件工程域
    ("代数学", "A"),
    ("代数几何", "A"),
    ("代数学", "A"),                     # 代数学域
    ("分析学", "N"),                     # 分析学域
    ("电动力学", "P"),
    ("统计物理", "P"),
    ("理论力学", "P"),
    ("场论", "P"),
    ("物理学", "P"),
    ("力学", "P"),                       # 系统物理域
    ("范畴论", "C"),                     # 范畴论域
    ("建模.*计算", "M"),                 # 建模与计算域
    ("离散", "D"),                       # 离散结构域
    ("合成生信", "S"),
    ("生物信息", "S"),                   # 合成生信域
    ("科学仪器", "SE"),                  # 科学仪器软件 -> 软件工程域
]


def _classify_domain(course_title: str) -> str:
    """根据课程标题关键词推断领域 ID"""
    for pattern, domain_id in _DOMAIN_KEYWORDS:
        if re.search(pattern, course_title):
            return domain_id
    # fallback: 尝试英文关键词
    title_en = course_title.lower()
    if any(kw in title_en for kw in ["algebra", "geometry", "topology"]):
        return "A"
    if any(kw in title_en for kw in ["physics", "mechanics", "field", "dynam"]):
        return "P"
    if any(kw in title_en for kw in ["algorithm", "data structure"]):
        return "DS"
    if any(kw in title_en for kw in ["operating system", "architecture", "compiler"]):
        return "CS"
    if any(kw in title_en for kw in ["circuit", "embedded"]):
        return "DE"
    if any(kw in title_en for kw in ["software", "engineering"]):
        return "SE"
    if any(kw in title_en for kw in ["category", "functor"]):
        return "C"
    if any(kw in title_en for kw in ["biology", "bioinfo"]):
        return "S"
    return "UNKNOWN"


def _ensure_thread(state: EcosystemState, domain: str,
                   domain_threads: Dict[str, str]) -> str:
    """确保某领域线程存在，返回 thread_id"""
    if domain in domain_threads:
        return domain_threads[domain]
    tid = f"thread_{domain}"
    domain_label = DOMAIN_NAMES.get(domain, domain)
    thread = ResearchThread(
        id=tid,
        label=domain_label,
        description=f"{domain_label}相关概念",
        concept_ids=[],
        clarity=0.4,
        momentum=0.7,
    )
    state.threads[tid] = thread
    domain_threads[domain] = tid
    return tid


def _add_to_thread(state: EcosystemState, thread_id: str, concept_id: str):
    if concept_id not in state.threads[thread_id].concept_ids:
        state.threads[thread_id].concept_ids.append(concept_id)


def _run_note_analysis(
    state: EcosystemState,
    notes: List[Tuple[str, str, str]],
    domain_threads: Dict[str, str],
    existing_labels: set,
) -> int:
    """笔记正文 → jieba 分词 → 新术语概念（归入笔记所在线程）"""
    from .operators.ingest import IngestOperator
    ingest = IngestOperator(state)
    concept_id_by_file: Dict[str, str] = {}
    for c in state.concepts.values():
        for r in c.source_refs:
            if r.source_type == "note" and r.file_path:
                concept_id_by_file[r.file_path] = c.id
    new_terms = 0

    for cdir, fname, fpath in notes:
        if fpath in state.parsed_notes:
            continue  # 已解析过的笔记跳过
        text = _strip_rmd_body(fpath)
        if not text or len(text) < 20:
            continue
        result = ingest.parse(text)
        note_rel_cid = concept_id_by_file.get(fpath)
        note_domain = _classify_domain(cdir)
        note_tid = _ensure_thread(state, note_domain, domain_threads) if note_domain != "UNKNOWN" else None

        for term in result.new_term_labels:
            if term in existing_labels:
                continue
            seeded = ingest.seed(term, source="note")
            if seeded:
                existing_labels.add(term)
                new_terms += 1
                if note_tid:
                    _add_to_thread(state, note_tid, seeded.id)
                if note_rel_cid:
                    seeded.related_ids[note_rel_cid] = 0.3
                    if note_rel_cid in state.concepts:
                        state.concepts[note_rel_cid].related_ids[seeded.id] = 0.3

        for cid in result.mentioned_concept_ids:
            c = state.concepts.get(cid)
            if c and not c.is_fossilized:
                c.depth = min(10.0, c.depth + 0.1)
                c.freshness = min(1.0, c.freshness + 0.15)
                if note_rel_cid and note_rel_cid != cid:
                    strength = result.mention_confidences.get(cid, 0.1)
                    c.related_ids[note_rel_cid] = max(c.related_ids.get(note_rel_cid, 0), strength)
                    if note_rel_cid in state.concepts:
                        state.concepts[note_rel_cid].related_ids[cid] = max(
                            state.concepts[note_rel_cid].related_ids.get(cid, 0), strength
                        )

        for cid_a, cid_b, strength in result.detected_connections:
            ca = state.concepts.get(cid_a)
            cb = state.concepts.get(cid_b)
            if ca and cb:
                ca.related_ids[cid_b] = max(ca.related_ids.get(cid_b, 0), strength)
                cb.related_ids[cid_a] = max(cb.related_ids.get(cid_a, 0), strength)

        state.parsed_notes.add(fpath)

    if new_terms > 0:
        logger.info(f"Note content analysis: parsed {len(notes)} notes, {new_terms} new terms")
        # 持久化已解析记录
        try:
            from .persistence import save
            save(state)
        except Exception:
            pass
    return new_terms


def run(workspace_dir: str, state: EcosystemState) -> int:
    """
    从 CourseTracker JSON + Notes/*.Rmd 同步概念到生态状态。
    幂等——跳过已存在的 label，只添加缺失的概念和 source_refs。
    始终运行（不跳过已保存的状态）。
    """
    courses = _read_courses_json(workspace_dir)
    notes = _scan_notes(workspace_dir)
    created = 0
    existing_labels = {c.label for c in state.concepts.values()}

    # ── 1. 课程 → 概念 ──
    domain_threads: Dict[str, str] = {}
    for t in state.threads.values():
        if t.id.startswith("thread_"):
            domain_threads[t.id.split("_", 1)[1]] = t.id

    for course in courses:
        cid = course.get("note_id", "") or _concept_id(course.get("course_title", ""), "course")
        title = course.get("course_title", "")
        domain = _classify_domain(title)
        if not title:
            continue

        if title not in existing_labels:
            course_concept = Concept(
                id=cid,
                label=title,
                depth=1.5,
                freshness=0.8,
                source_refs=[
                    SourceRef(source_type="course", source_id=cid, label=title),
                ],
            )
            state.concepts[course_concept.id] = course_concept
            existing_labels.add(title)
            created += 1
        else:
            course_concept = next(c for c in state.concepts.values() if c.label == title)

        if not any(r.source_type == "course" and r.source_id == cid for r in course_concept.source_refs):
            course_concept.bind_source(source_type="course", source_id=cid, label=title)

        tid = _ensure_thread(state, domain, domain_threads)
        _add_to_thread(state, tid, course_concept.id)

        for lesson in course.get("lessons", []):
            ln = lesson.get("lesson_number", 0)
            lt = lesson.get("lesson_title", "")
            if not lt:
                continue
            lesson_label = f"L{ln} {lt}"
            if lesson_label in existing_labels:
                continue
            lid = _concept_id(lt, f"l{ln}")
            lesson_concept = Concept(
                id=lid,
                label=lesson_label,
                aliases=[lt, f"课时{ln}"],
                depth=0.8,
                freshness=0.6,
                parent_ids=[course_concept.id],
                source_refs=[
                    SourceRef(source_type="course", source_id=cid, label=lesson_label),
                ],
                related_ids={course_concept.id: 0.6},
            )
            for _cdir, fname, fpath in notes:
                if f"L{ln}" in fname or lt[:6] in fname:
                    lesson_concept.source_refs.append(
                        SourceRef(source_type="note", file_path=fpath, label=fname)
                    )
                    break
            state.concepts[lid] = lesson_concept
            existing_labels.add(lesson_label)
            course_concept.child_ids.append(lid)
            # 课时概念也归入领域线程
            _add_to_thread(state, tid, lid)
            created += 1

    # ── 2. 未被课程匹配的笔记 → 独立概念（加入对应领域线程） ──
    matched_notes = set()
    for c in state.concepts.values():
        for r in c.source_refs:
            if r.source_type == "note" and r.file_path:
                matched_notes.add(r.file_path)

    for cdir, fname, fpath in notes:
        if fpath in matched_notes:
            continue
        note_label = fname.replace(".Rmd", "")
        if note_label in existing_labels:
            continue
        nid = _concept_id(note_label, "note")
        note_concept = Concept(
            id=nid,
            label=note_label,
            depth=0.5,
            freshness=0.5,
            source_refs=[SourceRef(source_type="note", file_path=fpath, label=fname)],
        )
        state.concepts[nid] = note_concept
        existing_labels.add(note_label)
        # 按目录名分类到领域线程
        note_domain = _classify_domain(cdir)
        if note_domain != "UNKNOWN":
            ntid = _ensure_thread(state, note_domain, domain_threads)
            _add_to_thread(state, ntid, nid)
        created += 1

    # 只有新增了课程/笔记才运行 jieba 重解析
    if created > 0:
        try:
            created += _run_note_analysis(state, notes, domain_threads, existing_labels)
        except ImportError:
            logger.warning("IngestOperator not available, skipping note content analysis")
        except Exception as e:
            logger.warning(f"Note content analysis failed: {e}")

    # ── 4. 玩家初始位置 ──
    if created > 0 and not state.player.current_concept_id:
        first_cid = next(iter(state.concepts.keys()), None)
        if first_cid:
            state.player.current_concept_id = first_cid
            state.player.total_concepts_encountered = created
    elif created > 0:
        state.player.total_concepts_encountered += created

    logger.info(f"CourseTracker sync: created {created} new concepts "
                f"(total {len(state.concepts)}), {len(state.threads)} threads")
    return created
