"""
多语言翻译系统 - 快速本地化方案
支持中文、英文等多种语言
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class Translator:
    """翻译器核心类"""
    
    def __init__(self, locale_dir: Optional[Path] = None):
        self.locale_dir = locale_dir or Path(__file__).parent / "locales"
        self.locale_dir.mkdir(exist_ok=True)
        
        self.current_language = "zh-CN"
        self.translations: Dict[str, Dict[str, str]] = {}
        
        self._load_translations()
    
    def _load_translations(self):
        """加载所有翻译文件"""
        # 加载默认翻译
        self._load_default_translations()
        
        # 加载外部翻译文件
        if self.locale_dir.exists():
            for file in self.locale_dir.glob("*.json"):
                lang_code = file.stem
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if lang_code not in self.translations:
                            self.translations[lang_code] = {}
                        self.translations[lang_code].update(data)
                    logger.info(f"加载翻译文件: {file.name}")
                except Exception as e:
                    logger.error(f"加载翻译文件失败 {file.name}: {e}")
    
    def _load_default_translations(self):
        """加载默认翻译（内置）"""
        # 默认中文翻译
        self.translations["zh-CN"] = {
            "config.title": "WS2 Agent 配置中心",
            "config.subtitle": "管理您的 API 提供商和工具",
            "config.save_close": "保存并关闭",
            "config.test": "测试配置",
            "provider.title": "已配置的提供商",
            "provider.add": "➕ 添加",
            "provider.edit": "✏️ 编辑",
            "provider.delete": "🗑️ 删除",
            "provider.quick": "快捷添加",
            "provider.details": "提供商详情",
            "provider.tips": "💡 提示",
            "tools.title": "工具配置",
            "tools.categories": "工具分类",
            "tools.list": "可用工具列表（可多选）",
            "tools.enable_selected": "✅ 启用选中",
            "tools.disable_selected": "❌ 禁用选中",
            "tools.enable_all": "✅ 全部启用",
            "tools.disable_all": "❌ 全部禁用",
            "tools.advanced": "高级工具配置",
            "rag.title": "📚 RAG 检索系统",
            "rag.add_doc": "添加文档到向量库",
            "rag.view_stats": "查看向量库状态",
            "sandbox.title": "🔒 沙箱执行",
            "sandbox.config": "配置安全策略",
            "sandbox.view_logs": "查看执行日志",
            "mcp.title": "🔌 MCP 客户端",
            "mcp.connect": "连接新 MCP 服务",
            "mcp.view_status": "查看连接状态",
            "skills.title": "技能配置",
            "skills.list": "可用技能列表",
            "skills.info": "技能说明",
            "skills.desc": "技能是可复用的功能模块，Agent 可以通过 skill_manager 工具来调用这些技能。",
            "approval.title": "🔒 审批管理",
            "approval.mode": "审批模式",
            "approval.pending": "待审批请求",
            "approval.approve": "✅ 批准选中",
            "approval.deny": "❌ 拒绝选中",
            "approval.refresh": "🔄 刷新",
            "approval.always": "总是批准的工具",
            "workflow.title": "⚡ 工作流管理",
            "workflow.definitions": "工作流定义",
            "workflow.create_sample": "➕