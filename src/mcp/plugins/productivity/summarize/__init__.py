import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

SUMMARIZE_SCHEMA = {
    "name": "summarize_tool",
    "description": "文本摘要工具。统计字数、提取关键词、生成结构化摘要。支持直接文本或文件路径输入。",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "待摘要的文本内容",
            },
            "file_path": {
                "type": "string",
                "description": "待摘要的文件路径（与text二选一）",
            },
            "mode": {
                "type": "string",
                "enum": ["brief", "structured", "academic"],
                "description": "摘要模式：brief=简要, structured=结构化, academic=学术, 默认structured",
            },
            "max_keywords": {
                "type": "integer",
                "description": "最大关键词数，默认10",
            },
        },
    },
}

_STOP_WORDS = {
    "en": {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
           "have", "has", "had", "do", "does", "did", "will", "would", "could",
           "should", "may", "might", "shall", "can", "need", "dare", "ought",
           "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
           "as", "into", "through", "during", "before", "after", "above", "below",
           "between", "out", "off", "over", "under", "again", "further", "then",
           "once", "here", "there", "when", "where", "why", "how", "all", "each",
           "every", "both", "few", "more", "most", "other", "some", "such", "no",
           "not", "only", "own", "same", "so", "than", "too", "very", "just",
           "because", "but", "and", "or", "if", "while", "about", "up", "its",
           "it", "this", "that", "these", "those", "i", "me", "my", "we", "our",
           "you", "your", "he", "him", "his", "she", "her", "they", "them", "their",
           "what", "which", "who", "whom", "whose", "also", "however"},
    "zh": {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
           "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
           "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
           "什么", "怎么", "如何", "可以", "因为", "所以", "但是", "而且", "或者",
           "如果", "虽然", "不过", "已经", "还", "又", "再", "把", "被", "让",
           "给", "对", "从", "向", "与", "及", "等", "之", "其", "此", "该",
           "以", "为", "中", "里", "后", "前", "时", "年", "月", "日"},
}


def _extract_keywords(text: str, max_keywords: int = 10) -> list:
    zh_pattern = re.compile(r'[\u4e00-\u9fff]{2,}')
    en_pattern = re.compile(r'[a-zA-Z][a-zA-Z0-9_-]{2,}')

    zh_words = zh_pattern.findall(text)
    en_words = [w.lower() for w in en_pattern.findall(text)]

    en_stop = _STOP_WORDS["en"]
    zh_stop = _STOP_WORDS["zh"]

    en_filtered = [w for w in en_words if w not in en_stop]
    zh_filtered = [w for w in zh_words if w not in zh_stop]

    counter = Counter(en_filtered + zh_filtered)
    return [word for word, _ in counter.most_common(max_keywords)]


def _split_sentences(text: str) -> list:
    parts = re.split(r'[。！？\.\!\?\n]+', text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]


def _brief_summary(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text[:200]
    n = min(3, len(sentences))
    return "。".join(sentences[:n]) + "。"


def _structured_summary(text: str, keywords: list) -> dict:
    sentences = _split_sentences(text)
    char_count = len(text)
    word_count = len(text.split())
    sentence_count = len(sentences)
    return {
        "char_count": char_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "keywords": keywords,
        "key_sentences": sentences[:5] if sentences else [],
    }


def _handle_summarize(args: dict, **kw) -> str:
    text = args.get("text", "")
    file_path = args.get("file_path", "")

    if file_path:
        try:
            path = Path(file_path).expanduser()
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
            else:
                return json.dumps({"success": False, "error": f"File not found: {file_path}"})
        except Exception as exc:
            return json.dumps({"success": False, "error": f"Failed to read file: {exc}"})

    if not text.strip():
        return json.dumps({"success": False, "error": "No text provided (use 'text' or 'file_path')"})

    mode = args.get("mode", "structured")
    max_keywords = max(1, int(args.get("max_keywords", 10)))
    keywords = _extract_keywords(text, max_keywords)

    if mode == "brief":
        summary = _brief_summary(text)
        return json.dumps({
            "success": True,
            "mode": "brief",
            "summary": summary,
            "keywords": keywords,
            "char_count": len(text),
        })

    result = _structured_summary(text, keywords)

    if mode == "academic":
        sentences = _split_sentences(text)
        result["academic_structure"] = {
            "background": sentences[0] if len(sentences) > 0 else "",
            "method_hint": sentences[1] if len(sentences) > 1 else "",
            "result_hint": sentences[2] if len(sentences) > 2 else "",
            "conclusion_hint": sentences[-1] if sentences else "",
        }

    return json.dumps({"success": True, "mode": mode, **result})


def register(ctx) -> None:
    ctx.register_tool(
        name="summarize_tool",
        toolset="summarize-tool",
        schema=SUMMARIZE_SCHEMA,
        handler=_handle_summarize,
        emoji="📝",
    )
    logger.info("summarize-tool plugin registered")
