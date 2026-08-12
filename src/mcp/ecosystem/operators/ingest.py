"""
文本解析管线——底层机制。

被调用者：
  - record 算子（用户主动输入）
  - observe 算子（自动处理 TS2 GatewayEvent）

职责：
  1. 扫描文本中的已知概念（关键词匹配）
  2. 检测新术语（未在知识图谱中出现过的）
  3. 识别活动类型（从句式结构推断）
  4. 检测概念之间的潜在连接
"""

import re
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from ..models import Concept, EcosystemState

logger = logging.getLogger(__name__)


# 活动类型 → 中文/英文关键词
@dataclass
class IngestResult:
    """
    解析管线输出
    """
    mentioned_concept_ids: List[str] = field(default_factory=list)
    mention_confidences: Dict[str, float] = field(default_factory=dict)
    new_term_labels: List[str] = field(default_factory=list)
    detected_activities: List[str] = field(default_factory=list)
    detected_connections: List[Tuple[str, str, float]] = field(default_factory=list)
    narrative: str = ""


_ACTIVITY_PATTERNS: Dict[str, List[str]] = {
    "reading": [
        "读", "阅读", "看", "翻阅", "浏览", "read", "reading",
        "看了", "读过", "翻看", "查阅", "查资料",
    ],
    "writing": [
        "写", "写作", "撰写", "整理", "记录", "write", "writing",
        "编辑", "修改", "起草", "草稿", "写了",
    ],
    "experiment": [
        "实验", "测试", "试验", "跑", "运行", "run", "experiment",
        "跑了", "运行了", "测试了", "验证", "复现",
    ],
    "discussion": [
        "讨论", "交流", "聊", "对话", "探讨", "商量", "discuss",
        "讨论了", "聊了", "探讨了", "会议", "meeting",
    ],
    "course": [
        "上课", "课程", "课", "讲座", "class", "lecture", "course",
        "学习", "学了", "听课", "听讲",
    ],
    "coding": [
        "代码", "编程", "写代码", "程序", "code", "coding", "program",
        "写了代码", "调试", "debug", "开发",
    ],
    "thinking": [
        "想", "思考", "琢磨", "反思", "think", "thinking",
        "想了想", "考虑", "灵感", "idea", "想法",
    ],
}


class IngestOperator:
    """
    文本解析管线

    三层递进策略：
      1. 关键词匹配：逐词匹配已知概念的 label 和 alias
      2. 新术语检测：找出不在知识图谱中的名词性短语
      3. 活动模式识别：从句式结构推断用户活动类型
    """

    def __init__(self, state: EcosystemState):
        self.state = state
        # 按 label 长度降序排列的概念列表（长词优先匹配）
        self._sorted_concepts: List[Concept] = []
        self._rebuild_index()

    def _rebuild_index(self):
        """重建排序索引（在概念增删后调用）"""
        self._sorted_concepts = sorted(
            [c for c in self.state.concepts.values() if c.is_alive],
            key=lambda c: len(c.label), reverse=True,
        )

    def parse(self, content: str, scene: str = "") -> IngestResult:
        """
        解析一段自由文本。

        Args:
            content: 用户输入的文本
            scene: 当前场景（"实验室""图书馆""讨论室"等）

        Returns:
            IngestResult: 解析结果
        """
        if not content or not content.strip():
            return IngestResult(narrative="空文本")

        result = IngestResult()

        # 1. 关键词匹配
        matches = self._match_keywords(content)
        for cid, conf in matches:
            if cid not in result.mentioned_concept_ids:
                result.mentioned_concept_ids.append(cid)
            result.mention_confidences[cid] = max(
                result.mention_confidences.get(cid, 0), conf
            )

        # 2. 活动检测（在关键词匹配之前做，避免被替换影响）
        result.detected_activities = self._detect_activities(content)
        if scene:
            result.detected_activities.insert(0, f"scene:{scene}")

        # 3. 新术语检测
        known_labels = set()
        for c in self.state.concepts.values():
            known_labels.add(c.label.lower())
            for a in c.aliases:
                known_labels.add(a.lower())
        result.new_term_labels = self._detect_new_terms(content, known_labels)

        # 4. 连接检测
        if len(result.mentioned_concept_ids) >= 2:
            result.detected_connections = self._detect_connections(
                content, result.mentioned_concept_ids
            )

        # 5. 组装 narrative
        parts = []
        if result.detected_activities:
            parts.append(f"活动: {', '.join(result.detected_activities[:3])}")
        if result.mentioned_concept_ids:
            labels = []
            for cid in result.mentioned_concept_ids[:5]:
                c = self.state.concepts.get(cid)
                if c:
                    labels.append(c.label)
            parts.append(f"提及: {', '.join(labels)}")
        if result.new_term_labels:
            parts.append(f"新术语: {', '.join(result.new_term_labels[:3])}")
        result.narrative = " | ".join(parts) if parts else "解析完成，未发现已知概念"

        return result

    def _match_keywords(self, content: str) -> List[Tuple[str, float]]:
        """
        逐词匹配已知概念 label 和 alias。

        策略：
          - 按 label 长度降序匹配（长词优先）
          - 支持中文子串匹配（中文无空格分词）
          - 英文做简单的 word boundary 检查
        """
        matches: List[Tuple[str, float]] = []
        content_lower = content.lower()

        for concept in self._sorted_concepts:
            if concept.id in [m[0] for m in matches]:
                continue

            # 检查 label
            label_lower = concept.label.lower()
            if label_lower in content_lower:
                # 英文词需要 word boundary 检查
                if label_lower[0].isascii():
                    pattern = r'\b' + re.escape(label_lower) + r'\b'
                    if re.search(pattern, content_lower):
                        confidence = len(label_lower) / max(len(content), 1)
                        confidence = min(1.0, confidence * 3 + 0.5)
                        matches.append((concept.id, confidence))
                        continue
                else:
                    # 中文直接匹配
                    confidence = len(label_lower) / max(len(content), 1)
                    confidence = min(1.0, confidence * 3 + 0.5)
                    matches.append((concept.id, confidence))
                    continue

            # 检查 aliases
            for alias in concept.aliases:
                alias_lower = alias.lower()
                if alias_lower in content_lower:
                    confidence = len(alias_lower) / max(len(content), 1)
                    confidence = min(1.0, confidence * 2 + 0.3)
                    matches.append((concept.id, confidence))
                    break

        return matches

    def _detect_new_terms(self, content: str,
                          known_labels: Set[str]) -> List[str]:
        """
        找出不在已知概念中的名词性短语。

        策略：
          1. 引号内容优先（最高优先级）
          2. 英文专有名词
          3. jieba 分词提取中文名词性短语 + TF-IDF 关键词
          4. 去重（长词包含短词时只保留长词）
          5. 最多返回 5 个
        """
        candidates: Dict[str, int] = {}

        for match in re.finditer(r'"([^"]{2,})"', content):
            term = match.group(1).strip()
            if term.lower() not in known_labels:
                candidates[term] = candidates.get(term, 0) + 3

        for match in re.finditer(r'\b([A-Z][a-z]{2,}(?:\s[A-Z][a-z]+)*)\b', content):
            term = match.group(1)
            if term.lower() not in known_labels and len(term) >= 3:
                candidates[term] = candidates.get(term, 0) + 2

        for match in re.finditer(r'(?<=[\u4e00-\u9fff])([A-Z][a-z]{2,})(?=[\u4e00-\u9fff])', content):
            term = match.group(1)
            if term.lower() not in known_labels and len(term) >= 3:
                candidates[term] = candidates.get(term, 0) + 2

        try:
            import jieba
            import jieba.analyse
        except ImportError:
            return self._fallback_new_terms(content, known_labels, candidates)

        noun_starts = set(
            "量机神经网络统计计算理论模型算法系统结构函数数论动力"
            "优化深度强化学习分析方法应用技术工程生物化学物理材料"
            "密码信息控制决策规划视觉语言知识推理逻辑概率随机分布"
            "分类回归预测诊断评估管理策略机制动力学耦合反馈循环"
            "量子纠缠相干退相干扰动近似渐近解析数值纠研究中"
        )

        # jieba 精确分词
        words = jieba.lcut(content)

        # 提取 ≥ 2 字且以名词起首字的词
        for w in words:
            if len(w) < 2:
                continue
            if w.lower() in known_labels or self._is_stop_word(w):
                continue
            if w[0] in noun_starts:
                candidates[w] = candidates.get(w, 0) + 2

        # 合并连续名词性词（"量子"+"纠缠"→"量子纠缠"），最长 6 字
        i = 0
        while i < len(words):
            if (len(words[i]) >= 2 and words[i][0] in noun_starts
                    and words[i].lower() not in known_labels):
                merged = words[i]
                j = i + 1
                while j < len(words):
                    if len(merged) + len(words[j]) > 6:
                        break
                    if (len(words[j]) >= 2 and words[j][0] in noun_starts
                            and words[j].lower() not in known_labels):
                        merged += words[j]
                        j += 1
                    else:
                        break
                if len(merged) > len(words[i]):
                    candidates[merged] = candidates.get(merged, 0) + 3
                i = j
            else:
                i += 1

        # TF-IDF 关键词提取
        try:
            keywords = jieba.analyse.extract_tags(content, topK=5, allowPOS=('n', 'ns', 'nz', 'vn', 'l', 'eng'))
            for kw in keywords:
                if len(kw) >= 2 and kw.lower() not in known_labels and not self._is_stop_word(kw):
                    candidates[kw] = candidates.get(kw, 0) + 1
        except Exception:
            pass

        terms = sorted(candidates.keys(), key=len, reverse=True)
        filtered = []
        for t in terms:
            stripped = t
            while len(stripped) > 3 and stripped[-1] in "中里上下内外前后左右间":
                stripped = stripped[:-1]
            if stripped != t and stripped in candidates:
                t = stripped
            if not any(t != u and t in u for u in terms):
                filtered.append(t)

        return filtered[:5]

    def _fallback_new_terms(self, content: str, known_labels: Set[str],
                            existing: Dict[str, int]) -> List[str]:
        """无 jieba 时的滑动窗口后备方案"""
        noun_starts = set(
            "量机神经网络统计计算理论模型算法系统结构函数数论动力"
            "优化深度强化学习分析方法应用技术工程生物化学物理材料"
            "密码信息控制决策规划视觉语言知识推理逻辑概率随机分布"
            "分类回归预测诊断评估管理策略机制动力学耦合反馈循环"
            "量子纠缠相干退相干扰动近似渐近解析数值纠研究中"
        )
        text_only = re.sub(
            r'[的了是在于过这那和与或就把会被可有能已很比较着是都也而]',
            '\x00', content
        )
        segments = re.split(r'\x00+', text_only)
        for seg in segments:
            run_match = re.search(r'[\u4e00-\u9fff]{3,}', seg)
            if not run_match:
                continue
            run = run_match.group()
            for i in range(len(run)):
                for j in range(i + 3, min(i + 7, len(run) + 1)):
                    term = run[i:j]
                    if term.lower() in known_labels:
                        continue
                    if self._is_stop_word(term):
                        continue
                    if term[0] in noun_starts:
                        existing[term] = existing.get(term, 0) + 1

        terms = sorted(existing.keys(), key=len, reverse=True)
        filtered = []
        for t in terms:
            stripped = t
            while len(stripped) > 3 and stripped[-1] in "中里上下内外前后左右间":
                stripped = stripped[:-1]
            if stripped != t and stripped in existing:
                t = stripped
            if not any(t != u and t in u for u in terms):
                filtered.append(t)

        return filtered[:5]

    def _is_stop_word(self, word: str) -> bool:
        """判断是否为停用词"""
        stop_words = {
            "但是", "因为", "所以", "如果", "而且", "虽然", "然后",
            "可以", "这个", "那个", "什么", "怎么", "他们", "我们",
            "一个", "没有", "不是", "就是", "还是", "或者", "并且",
            "已经", "知道", "问题", "可能", "需要", "通过", "关于",
            "情况", "方法", "方式", "过程", "结果", "领域", "概念",
            "东西", "事情", "时候", "非常", "比较", "之间", "之后",
            "以及", "其中", "很多", "这些", "那些", "一些", "这样",
            "研究", "分析", "讨论", "验证", "实验", "测试", "使用",
            "应用", "提供", "进行", "实现", "提出", "采用", "利用",
            "发现", "表明", "说明", "证明", "描述", "定义", "给出",
            "证实", "计算", "处理", "优化", "训练", "学习", "预测",
        }
        return word in stop_words

    def _detect_activities(self, content: str) -> List[str]:
        """识别文本中的活动模式（避免已知概念子串误触发）"""
        found = []
        content_lower = content.lower()

        known_labels_lower = {
            c.label.lower()
            for c in self.state.concepts.values()
        }

        for activity, keywords in _ACTIVITY_PATTERNS.items():
            matched = False
            for kw in keywords:
                kw_lower = kw.lower()
                start = 0
                while start <= len(content_lower):
                    pos = content_lower.find(kw_lower, start)
                    if pos == -1:
                        break
                    # 检查此位置是否在已知概念标签内部（防"机器学习"→"学习"误判）
                    inside_known = False
                    for known in known_labels_lower:
                        if kw_lower != known and kw_lower in known:
                            kpos = content_lower.find(known)
                            while kpos != -1:
                                if kpos <= pos < kpos + len(known):
                                    inside_known = True
                                    break
                                kpos = content_lower.find(known, kpos + 1)
                            if inside_known:
                                break
                    if not inside_known:
                        matched = True
                        break
                    start = pos + len(kw_lower)
                if matched:
                    break
            if matched:
                found.append(activity)

        return found

    def _detect_connections(
        self, content: str, mentioned_ids: List[str]
    ) -> List[Tuple[str, str, float]]:
        """
        检测文本中提及的概念之间的潜在关系。

        规则：
          - 同一句子中同时出现的两个概念 → 连接强度 +0.1
          - 被"和""与""以及"连接的 → 连接强度 +0.2
        """
        connections: List[Tuple[str, str, float]] = []
        id_set = set(mentioned_ids)

        sentences = re.split(r'[。！？.!?\n]', content)
        for sent in sentences:
            sent_ids = []
            for cid in id_set:
                c = self.state.concepts.get(cid)
                if not c:
                    continue
                if self._has_whole_word(sent, c.label):
                    sent_ids.append(cid)
                    continue
                for alias in c.aliases:
                    if self._has_whole_word(sent, alias):
                        sent_ids.append(cid)
                        break

            for i in range(len(sent_ids)):
                for j in range(i + 1, len(sent_ids)):
                    strength = 0.15
                    ci = self.state.concepts.get(sent_ids[i])
                    cj = self.state.concepts.get(sent_ids[j])
                    if ci and cj:
                        if re.search(rf'{re.escape(ci.label)}\s*[和与以及]\s*{re.escape(cj.label)}', sent):
                            strength = 0.3
                    connections.append((sent_ids[i], sent_ids[j], strength))

        return connections

    def _has_whole_word(self, text: str, word: str) -> bool:
        """检查 word 在 text 中作为整词出现（非其他中文字符的子串）。"""
        word_lower = word.lower()
        text_lower = text.lower()
        start = 0
        while True:
            pos = text_lower.find(word_lower, start)
            if pos == -1:
                return False
            # 检查前后是否有中文字符（整词边界）
            before_ok = (pos == 0 or not ('\u4e00' <= text[pos-1] <= '\u9fff'))
            after_pos = pos + len(word)
            after_ok = (after_pos >= len(text) or not ('\u4e00' <= text[after_pos] <= '\u9fff'))
            if before_ok and after_ok:
                return True
            start = pos + len(word)
        return False

    def reinforce(self, concept_id: str, amount: float = 0.3) -> bool:
        """加固一个已知概念"""
        concept = self.state.concepts.get(concept_id)
        if not concept or concept.is_fossilized:
            return False
        concept.depth = min(10.0, concept.depth + amount)
        concept.freshness = min(1.0, concept.freshness + amount)
        concept.updated_at = time.time()
        return True

    def seed(self, label: str, source: str = "record") -> Optional[Concept]:
        """创建一个新概念种子"""
        label = label.strip()
        if not label:
            return None

        concept = Concept(
            id=uuid.uuid4().hex[:12],
            label=label,
            depth=0.5,
            freshness=1.0,
            entropy=0.15,  # 新种子有少量固有熵
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.state.concepts[concept.id] = concept
        self._rebuild_index()
        logger.info(f"Ingest seeded new concept: {label} ({concept.id})")
        return concept
