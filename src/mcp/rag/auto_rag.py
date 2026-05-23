#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动 RAG 集成系统
在 Agent 处理用户问题前自动检索相关上下文，提升回答质量和效率
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from .rag_engine import RAGEngine, create_rag_engine


@dataclass
class RetrievalConfig:
    """检索配置"""
    enabled: bool = True
    auto_trigger: bool = True
    top_k: int = 4
    min_score_threshold: float = 0.1
    max_context_length: int = 2000
    include_metadata: bool = True
    cache_retrievals: bool = True


class AutoRAGManager:
    """
    自动 RAG 管理器
    - 在 Agent 处理前自动检索上下文
    - 智能判断何时需要检索
    - 缓存检索结果提升性能
    """
    
    def __init__(
        self,
        rag_engine: Optional[RAGEngine] = None,
        config: Optional[RetrievalConfig] = None,
        persist_dir: Optional[Path] = None
    ):
        self.config = config or RetrievalConfig()
        self.rag_engine = rag_engine
        self.persist_dir = persist_dir
        self._retrieval_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._query_cache: Dict[str, float] = {}
        
        # 加载缓存
        self._load_cache()
        
        # 常见的需要检索的关键词模式
        self._retrieval_trigger_patterns = [
            r'(?i)\b(什么是|如何|怎样|怎么|为什么|哪个|哪些|哪里|何时)\b',
            r'(?i)\b(解释|说明|介绍|讲述|讲解|描述|定义)\b',
            r'(?i)\b(告诉我|告诉我|请教|问一下|查询)\b',
            r'(?i)\b(课程|笔记|资料|文档|内容)\b',
            r'(?i)\b(记得|回想|之前|上次|过去)\b',
            r'^[^\n]{5,}$',  # 超过5个字符的查询
        ]
    
    def should_retrieve(self, query: str) -> bool:
        """
        判断是否需要执行检索
        """
        if not self.config.enabled or not self.config.auto_trigger:
            return False
        
        # 如果没有内容，不检索
        if self.rag_engine and self.rag_engine.get_document_count() == 0:
            return False
        
        # 检查触发模式
        for pattern in self._retrieval_trigger_patterns:
            if re.search(pattern, query):
                return True
        
        # 查询太长也触发
        if len(query) > 30:
            return True
        
        return False
    
    def inject_context(self, query: str, system_prompt: Optional[str] = None) -> Tuple[str, bool]:
        """
        将检索到的上下文注入到系统提示词或查询中
        返回: (增强后的查询/系统提示词, 是否有检索结果)
        """
        if not self.should_retrieve(query):
            return query or system_prompt or "", False
        
        context_str, results = self.retrieve(query)
        
        if not context_str:
            return query or system_prompt or "", False
        
        if system_prompt:
            # 注入到系统提示词
            enhanced_prompt = f"""{system_prompt}

【知识库上下文】
{context_str}
"""
            return enhanced_prompt, True
        else:
            # 注入到用户查询
            enhanced_query = f"""【知识库上下文】
{context_str}

【用户问题】
{query}
"""
            return enhanced_query, True
    
    def _format_context(self, results: List[Dict[str, Any]], max_content_len: int = 2000) -> str:
        """
        格式化检索结果为易读的字符串（安全版本）
        """
        if not results:
            return ""
        
        lines = []
        total_len = 0
        
        for i, doc in enumerate(results, 1):
            content = doc.get("content", "") or ""
            source = doc.get("source", "") or doc.get("metadata", {}).get("file_name", f"文档 {i}") or f"文档 {i}"
            
            # 安全处理：截断过长内容，清理特殊字符
            if len(content) > max_content_len:
                content = content[:max_content_len - 3] + "..."
            
            # 清理可能破坏Markdown格式的字符
            safe_content = content.replace('\\', '\\\\').replace('`', '\\`').replace('*', '\\*')
            safe_source = str(source).replace('`', '\\`').replace('*', '\\*')[:100]
            
            line = f"【{i}】{safe_source}\n{safe_content}\n"
            total_len += len(line)
            
            # 防止总长度过大
            if total_len > 8000:
                lines.append(f"【{i}】{safe_source}\n[内容已截断]\n")
                break
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def _get_cache_key(self, query: str) -> str:
        """
        生成缓存键
        """
        # 简单的归一化：转小写，去除空格
        normalized = re.sub(r'\s+', ' ', query.strip().lower())
        return normalized
    
    def add_knowledge_from_ws2(self, ws2_system=None) -> int:
        """
        从 WS2 系统中自动加载课程、笔记等知识
        返回添加的文档数量
        """
        if not self.rag_engine:
            return 0
        
        added_count = 0
        
        # 方法1：从 db_paths 加载文件系统中的文档
        if hasattr(ws2_system, 'db_paths'):
            for db_path in ws2_system.db_paths:
                try:
                    path = Path(db_path)
                    if path.is_dir():
                        result = self.rag_engine.add_directory(str(path))
                        added_count += len(result)
                    elif path.suffix in ['.md', '.txt', '.json']:
                        self.rag_engine.add_file(str(path))
                        added_count += 1
                except Exception as e:
                    print(f"添加知识失败: {e}")
        
        # 方法2：从 ws2_system.courses 直接导入课程信息
        if hasattr(ws2_system, 'courses'):
            for course in ws2_system.courses:
                try:
                    text = self._format_course_for_rag(course)
                    if text:
                        doc_id = self.rag_engine.add_text(
                            text,
                            metadata={
                                "source": "ws2_course",
                                "course_id": course.get("note_id", ""),
                                "course_title": course.get("course_title", ""),
                                "domain": course.get("domain", ""),
                            }
                        )
                        added_count += 1
                except Exception as e:
                    print(f"添加课程失败: {e}")
        
        # 方法3：从 ws2_system.notes 导入笔记内容
        if hasattr(ws2_system, 'notes') and ws2_system.notes:
            for note_id, note_content in ws2_system.notes.items():
                try:
                    if note_content and isinstance(note_content, str):
                        doc_id = self.rag_engine.add_text(
                            note_content,
                            metadata={
                                "source": "ws2_note",
                                "note_id": note_id,
                            }
                        )
                        added_count += 1
                except Exception as e:
                    print(f"添加笔记失败: {e}")
        
        # 方法4：从 ws2_system.bookmarks 导入书签
        if hasattr(ws2_system, 'bookmarks') and ws2_system.bookmarks:
            for bm in ws2_system.bookmarks:
                try:
                    text = f"书签: {bm.get('title', '')}\nURL: {bm.get('url', '')}\n分类: {bm.get('category', '')}"
                    doc_id = self.rag_engine.add_text(
                        text,
                        metadata={
                            "source": "ws2_bookmark",
                            "bookmark_id": bm.get('id', ''),
                        }
                    )
                    added_count += 1
                except Exception as e:
                    print(f"添加书签失败: {e}")
        
        return added_count
    
    def _format_course_for_rag(self, course: Dict[str, Any]) -> str:
        """将课程信息格式化为适合RAG的文本"""
        if not course:
            return ""
        
        lines = []
        
        # 标题
        title = course.get("course_title", "")
        if title:
            lines.append(f"【课程】{title}")
        
        # 领域
        domain = course.get("domain", "")
        if domain:
            lines.append(f"领域: {domain}")
        
        # 描述
        desc = course.get("description", "")
        if desc:
            lines.append(f"描述: {desc}")
        
        # 课时信息
        lessons = course.get("lessons", [])
        if lessons:
            lines.append(f"课时列表 ({len(lessons)} 个课时):")
            for lesson in lessons[:20]:  # 最多20个课时
                lesson_title = lesson.get("title", lesson.get("name", ""))
                if lesson_title:
                    lines.append(f"- {lesson_title}")
        
        # 资源
        resources = course.get("resources", [])
        if resources:
            lines.append(f"资源列表 ({len(resources)} 个):")
            for res in resources[:10]:  # 最多10个资源
                label = res.get("label", "")
                if label:
                    lines.append(f"- {label}")
        
        return "\n".join(lines) if lines else ""
    
    def clear_cache(self):
        """
        清空检索缓存
        """
        self._retrieval_cache.clear()
        self._query_cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取 RAG 系统统计
        """
        return {
            "enabled": self.config.enabled,
            "auto_trigger": self.config.auto_trigger,
            "document_count": self.rag_engine.get_document_count() if self.rag_engine else 0,
            "cache_size": len(self._retrieval_cache),
            "top_k": self.config.top_k,
        }
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索 RAG 知识库（兼容 ws2_tools 接口）
        返回包含 content, score, source 的结果列表
        """
        if not self.rag_engine:
            return []
        
        try:
            results = self.rag_engine.query(query, top_k)
            rag_results = []
            for doc in results.get("documents", []):
                content = doc.get("content", "")
                score = doc.get("metadata", {}).get("score", 0.0)
                source = doc.get("source", doc.get("metadata", {}).get("file_name", ""))
                rag_results.append({
                    "content": content,
                    "score": score,
                    "source": source
                })
            return rag_results
        except Exception as e:
            print(f"RAG search 失败: {e}")
            return []
    
    def get_context(self, query: str, top_k: int = 4) -> str:
        """
        获取 RAG 知识库的格式化上下文（兼容 ws2_tools 接口）
        返回格式化的上下文字符串
        """
        if not self.rag_engine:
            return ""
        
        try:
            return self.rag_engine.get_context_for_prompt(query, top_k)
        except Exception as e:
            print(f"RAG get_context 失败: {e}")
            return ""
    
    def _load_cache(self) -> None:
        """从磁盘加载检索缓存"""
        if not self.persist_dir or not self.config.cache_retrievals:
            return
        
        cache_file = self.persist_dir / "retrieval_cache.json"
        if cache_file.exists():
            try:
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._retrieval_cache = data.get("retrievals", {})
                    self._query_cache = data.get("queries", {})
            except Exception as e:
                print(f"加载RAG缓存失败: {e}")
    
    def _save_cache(self) -> None:
        """保存检索缓存到磁盘"""
        if not self.persist_dir or not self.config.cache_retrievals:
            return
        
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.persist_dir / "retrieval_cache.json"
            
            import json
            data = {
                "version": "1.0",
                "retrievals": self._retrieval_cache,
                "queries": self._query_cache,
                "saved_at": __import__('time').time()
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存RAG缓存失败: {e}")
    
    def retrieve(self, query: str, top_k: Optional[int] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        检索相关上下文，支持缓存
        """
        if not self.rag_engine:
            return "", []
        
        # 检查缓存
        cache_key = self._get_cache_key(query)
        if self.config.cache_retrievals and cache_key in self._retrieval_cache:
            cached_results = self._retrieval_cache[cache_key]
            return self._format_context(cached_results), cached_results
        
        # 执行检索
        results = self.rag_engine.query(query, top_k or self.config.top_k)
        doc_results = results.get("documents", [])
        
        # 过滤低分数结果
        filtered_results = []
        for doc in doc_results:
            score = doc.get("metadata", {}).get("score", 0.0)
            if score >= self.config.min_score_threshold:
                filtered_results.append(doc)
        
        # 缓存结果并保存
        if self.config.cache_retrievals:
            self._retrieval_cache[cache_key] = filtered_results
            self._save_cache()
        
        return self._format_context(filtered_results), filtered_results
    
    def clear_cache(self) -> None:
        """清空检索缓存"""
        self._retrieval_cache.clear()
        self._query_cache.clear()
        self._save_cache()
        if self.rag_engine:
            self.rag_engine.clear()


# 全局单例
_auto_rag_instance: Optional[AutoRAGManager] = None


def get_auto_rag(persist_dir: Optional[Path] = None) -> AutoRAGManager:
    """
    获取或创建 AutoRAG 管理器单例
    """
    global _auto_rag_instance
    if _auto_rag_instance is None:
        rag_engine = create_rag_engine(persist_directory=persist_dir)
        _auto_rag_instance = AutoRAGManager(rag_engine=rag_engine, persist_dir=persist_dir)
    return _auto_rag_instance


def initialize_rag_for_agent(base_path: str, ws2_system=None) -> AutoRAGManager:
    """
    为 Agent 初始化 RAG 系统
    """
    persist_dir = Path(base_path) / "rag_data" if base_path else None
    auto_rag = get_auto_rag(persist_dir)
    
    # 尝试从 WS2 系统加载知识
    if ws2_system:
        auto_rag.add_knowledge_from_ws2(ws2_system)
    
    return auto_rag
