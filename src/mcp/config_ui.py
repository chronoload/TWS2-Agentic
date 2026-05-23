#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 Agent 配置界面 - 完全重构，支持多源 API 提供商
类似 Cline 的配置体验，包含：
- 提供商选择器
- 模型配置
- 优先级管理
- 快捷配置助手
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, List
from pathlib import Path
import json

from .config import get_config_manager

# 安全导入 llm 模块中的提供商类型
try:
    from .llm import (
        ProviderType,
        ProviderConfig,
        PROVIDER_DISPLAY_NAMES,
        PROVIDER_DEFAULT_BASE_URL,
        PROVIDER_DEFAULT_MODELS,
        get_models_for_provider,
        create_default_provider_config,
    )
    HAS_PROVIDERS = True
except ImportError as e:
    HAS_PROVIDERS = False
    print(f"警告：无法导入 llm 模块: {e}")
    # 创建占位符
    class DummyProviderType:
        SIMULATOR = "simulator"
    ProviderType = DummyProviderType
    ProviderConfig = None
    PROVIDER_DISPLAY_NAMES = {}
    PROVIDER_DEFAULT_BASE_URL = {}
    PROVIDER_DEFAULT_MODELS = {}


class ProviderConfigDialog:
    """单个提供商配置对话框"""
    
    def __init__(self, parent, config: Optional[any] = None):
        self.parent = parent
        self.config = config
        self.result = None
        
        if not HAS_PROVIDERS:
            messagebox.showerror("错误", "llm_providers 模块未正确导入，无法使用配置界面")
            return
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("配置 API 提供商" if config else "添加新 API 提供商")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._create_widgets()
        if config:
            self._load_config(config)
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 提供商选择
        ttk.Label(main_frame, text="API 提供商", font=("", 10, "bold")).pack(anchor=tk.W)
        self.provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(
            main_frame, 
            textvariable=self.provider_var,
            values=[PROVIDER_DISPLAY_NAMES.get(p, p.value) for p in ProviderType] if HAS_PROVIDERS else [],
            state="readonly",
            width=50
        )
        provider_combo.pack(fill=tk.X, pady=(5, 15))
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)
        
        # 提供商名称映射
        self.provider_name_map = {PROVIDER_DISPLAY_NAMES.get(p, p.value): p for p in ProviderType} if HAS_PROVIDERS else {}
        
        # 配置表单
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置名称
        ttk.Label(form_frame, text="配置名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=5)
        
        # API Key
        ttk.Label(form_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        key_entry = ttk.Entry(form_frame, textvariable=self.api_key_var, show="*", width=40)
        key_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)
        
        # 显示/隐藏密码按钮
        self.show_key = False
        def toggle_key():
            self.show_key = not self.show_key
            key_entry.config(show="" if self.show_key else "*")
        ttk.Button(form_frame, text="👁", width=3, command=toggle_key).grid(row=1, column=2, padx=(5, 0))
        
        # Base URL
        ttk.Label(form_frame, text="Base URL:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.base_url_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.base_url_var, width=40).grid(row=2, column=1, sticky=tk.EW, pady=5)
        
        # 模型选择
        ttk.Label(form_frame, text="模型:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(form_frame, textvariable=self.model_var, width=37, state="readonly")
        self.model_combo.grid(row=3, column=1, sticky=tk.EW, pady=5)
        
        # 自定义模型输入
        ttk.Label(form_frame, text="或输入自定义模型:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.custom_model_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.custom_model_var, width=40).grid(row=4, column=1, sticky=tk.EW, pady=5)
        
        # 温度和最大 Token
        ttk.Label(form_frame, text="温度:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.temperature_var = tk.DoubleVar(value=0.7)
        ttk.Scale(form_frame, from_=0.0, to=2.0, variable=self.temperature_var, orient=tk.HORIZONTAL).grid(row=5, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(form_frame, text="最大 Token:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.max_tokens_var = tk.IntVar(value=4096)
        ttk.Spinbox(form_frame, from_=256, to=128000, textvariable=self.max_tokens_var, width=37).grid(row=6, column=1, sticky=tk.W, pady=5)
        
        # 优先级
        ttk.Label(form_frame, text="优先级:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.priority_var = tk.IntVar(value=0)
        ttk.Spinbox(form_frame, from_=0, to=100, textvariable=self.priority_var, width=37).grid(row=7, column=1, sticky=tk.W, pady=5)
        
        # 启用开关
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_frame, text="启用此配置", variable=self.enabled_var).grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        form_frame.columnconfigure(1, weight=1)
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(btn_frame, text="取消", command=self.dialog.destroy).pack(side=tk.RIGHT)
        
        # 设置默认提供商
        if not self.config and HAS_PROVIDERS:
            provider_combo.current(0)
            self._on_provider_changed(None)
    
    def _on_provider_changed(self, event):
        """提供商改变时更新默认配置"""
        if not HAS_PROVIDERS:
            return
        display_name = self.provider_var.get()
        provider = self.provider_name_map.get(display_name)
        if not provider:
            return
        
        # 设置默认值
        if not self.config:
            self.name_var.set(f"{display_name} 配置")
        
        base_url = PROVIDER_DEFAULT_BASE_URL.get(provider, "")
        if base_url:
            self.base_url_var.set(base_url)
        
        # 更新模型列表
        models = PROVIDER_DEFAULT_MODELS.get(provider, [])
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])
    
    def _load_config(self, config: any):
        """加载现有配置"""
        if not HAS_PROVIDERS:
            return
        display_name = PROVIDER_DISPLAY_NAMES.get(config.provider, config.provider.value) if hasattr(config.provider, 'value') else str(config.provider)
        self.provider_var.set(display_name)
        self.name_var.set(config.name or display_name)
        self.api_key_var.set(config.api_key)
        self.base_url_var.set(config.base_url or "")
        self.model_var.set(config.model)
        self.temperature_var.set(config.temperature)
        self.max_tokens_var.set(config.max_tokens)
        self.priority_var.set(config.priority)
        self.enabled_var.set(config.enabled)
        
        # 更新模型列表
        if hasattr(config.provider, 'value'):
            models = PROVIDER_DEFAULT_MODELS.get(config.provider, [])
            self.model_combo['values'] = models
            if config.model not in models and models:
                self.model_combo['values'] = models + [config.model]
    
    def _save(self):
        """保存配置"""
        if not HAS_PROVIDERS:
            messagebox.showerror("错误", "llm_providers 模块未正确导入")
            return
            
        display_name = self.provider_var.get()
        provider = self.provider_name_map.get(display_name)
        if not provider:
            messagebox.showwarning("警告", "请选择 API 提供商")
            return
        
        name = self.name_var.get().strip()
        if not name:
            name = display_name
        
        # 使用自定义模型或选择的模型
        model = self.custom_model_var.get().strip() or self.model_var.get()
        if not model:
            messagebox.showwarning("警告", "请选择或输入模型名称")
            return
        
        config = ProviderConfig(
            provider=provider,
            name=name,
            api_key=self.api_key_var.get(),
            base_url=self.base_url_var.get() or None,
            model=model,
            temperature=self.temperature_var.get(),
            max_tokens=self.max_tokens_var.get(),
            priority=self.priority_var.get(),
            enabled=self.enabled_var.get()
        )
        
        self.result = config
        self.dialog.destroy()


class EnhancedAgentConfigDialog:
    """增强版 Agent 配置对话框 - 类似 Cline 的体验"""
    
    def __init__(self, parent):
        self.parent = parent
        self.config_manager = get_config_manager()
        
        if not HAS_PROVIDERS:
            messagebox.showerror("错误", "llm_providers 模块未正确导入，无法使用配置界面")
            return
        
        self.window = tk.Toplevel(parent)
        self.window.title("WS2 Agent 配置中心")
        self.window.geometry("1000x700")
        
        self._create_widgets()
        self._refresh_ui()
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.window, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(title_frame, text="🤖 WS2 Agent 配置中心", font=("", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(title_frame, text="管理您的 API 提供商和工具", font=("", 10)).pack(side=tk.LEFT, padx=(15, 0))
        
        # 创建 Notebook
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # API 提供商标签页
        self._create_providers_tab(notebook)
        
        # 工具配置标签页
        self._create_tools_tab(notebook)
        
        # 设置标签页
        self._create_settings_tab(notebook)
        
        # 底部按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        ttk.Button(btn_frame, text="保存并关闭", command=self._save_and_close).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="测试配置", command=self._test_config).pack(side=tk.RIGHT, padx=(0, 10))
    
    def _create_providers_tab(self, notebook):
        """创建 API 提供商配置标签页"""
        if not HAS_PROVIDERS:
            return
            
        providers_frame = ttk.Frame(notebook, padding="10")
        notebook.add(providers_frame, text="🔌 API 提供商")
        
        # 分割面板
        paned = ttk.PanedWindow(providers_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：提供商列表
        left_frame = ttk.Frame(paned, padding=(0, 0, 10, 0))
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="已配置的提供商", font=("", 10, "bold")).pack(anchor=tk.W)
        
        # 列表框
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        self.provider_tree = ttk.Treeview(
            list_frame,
            columns=("priority", "name", "provider", "enabled"),
            show="headings",
            height=15
        )
        self.provider_tree.heading("priority", text="优先级")
        self.provider_tree.heading("name", text="名称")
        self.provider_tree.heading("provider", text="类型")
        self.provider_tree.heading("enabled", text="状态")
        self.provider_tree.column("priority", width=60, anchor=tk.CENTER)
        self.provider_tree.column("name", width=150)
        self.provider_tree.column("provider", width=120)
        self.provider_tree.column("enabled", width=60, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.provider_tree.yview)
        self.provider_tree.configure(yscrollcommand=scrollbar.set)
        
        self.provider_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.provider_tree.bind("<<TreeviewSelect>>", self._on_provider_select)
        
        # 列表按钮
        list_btn_frame = ttk.Frame(left_frame)
        list_btn_frame.pack(fill=tk.X)
        ttk.Button(list_btn_frame, text="➕ 添加", command=self._add_provider).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(list_btn_frame, text="✏️ 编辑", command=self._edit_provider).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        ttk.Button(list_btn_frame, text="🗑️ 删除", command=self._delete_provider).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # 快捷添加按钮
        quick_frame = ttk.LabelFrame(left_frame, text="快捷添加", padding="10")
        quick_frame.pack(fill=tk.X, pady=(10, 0))
        
        quick_providers = [
            (ProviderType.OPENAI, "OpenAI"),
            (ProviderType.DEEPSEEK, "DeepSeek"),
            (ProviderType.QWEN, "通义千问"),
            (ProviderType.ANTHROPIC, "Claude"),
            (ProviderType.GROQ, "Groq"),
            (ProviderType.OLLAMA, "Ollama"),
        ]
        
        for i, (provider, label) in enumerate(quick_providers):
            btn = ttk.Button(quick_frame, text=label, command=lambda p=provider: self._quick_add_provider(p))
            btn.grid(row=i//2, column=i%2, sticky=tk.EW, padx=2, pady=2)
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.columnconfigure(1, weight=1)
        
        # 右侧：提供商详情
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        ttk.Label(right_frame, text="提供商详情", font=("", 10, "bold")).pack(anchor=tk.W)
        
        self.detail_text = tk.Text(right_frame, wrap=tk.WORD, height=20)
        self.detail_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # 提示
        tip_frame = ttk.LabelFrame(right_frame, text="💡 提示", padding="10")
        tip_frame.pack(fill=tk.X, pady=(10, 0))
        tips = [
            "• 优先级数字越小，越优先使用",
            "• 可以同时配置多个提供商，实现自动故障转移",
            "• 模拟器提供商可以在没有真实 API 时测试界面",
        ]
        for tip in tips:
            ttk.Label(tip_frame, text=tip).pack(anchor=tk.W)
    
    def _create_tools_tab(self, notebook):
        """创建工具配置标签页"""
        from .tools import get_tools
        from .config import SkillConfig
        
        tools_frame = ttk.Frame(notebook, padding="10")
        notebook.add(tools_frame, text="🛠️ 工具配置")
        
        ttk.Label(tools_frame, text="可用工具", font=("", 10, "bold")).pack(anchor=tk.W)
        
        tree_frame = ttk.Frame(tools_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        self.tools_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "description", "enabled"),
            show="headings",
            height=20
        )
        self.tools_tree.heading("name", text="工具名称")
        self.tools_tree.heading("description", text="描述")
        self.tools_tree.heading("enabled", text="状态")
        self.tools_tree.column("name", width=200)
        self.tools_tree.column("description", width=400)
        self.tools_tree.column("enabled", width=80, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tools_tree.yview)
        self.tools_tree.configure(yscrollcommand=scrollbar.set)
        
        self.tools_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tools_btn_frame = ttk.Frame(tools_frame)
        tools_btn_frame.pack(fill=tk.X)
        ttk.Button(tools_btn_frame, text="启用选中", command=self._enable_selected_tool).pack(side=tk.LEFT)
        ttk.Button(tools_btn_frame, text="禁用选中", command=self._disable_selected_tool).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(tools_btn_frame, text="全部启用", command=self._enable_all_tools).pack(side=tk.LEFT, padx=(5, 0))
    
    def _create_settings_tab(self, notebook):
        """创建设置标签页"""
        settings_frame = ttk.Frame(notebook, padding="10")
        notebook.add(settings_frame, text="⚙️ 设置")
        
        # 导入/导出
        io_frame = ttk.LabelFrame(settings_frame, text="配置导入/导出", padding="15")
        io_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Button(io_frame, text="📤 导出配置", command=self._export_config).pack(side=tk.LEFT)
        ttk.Button(io_frame, text="📥 导入配置", command=self._import_config).pack(side=tk.LEFT, padx=(10, 0))
        
        # 默认提供商
        default_frame = ttk.LabelFrame(settings_frame, text="默认设置", padding="15")
        default_frame.pack(fill=tk.X)
        
        ttk.Label(default_frame, text="首次使用建议：先配置一个 API 提供商，然后测试连接").pack(anchor=tk.W)
    
    def _refresh_ui(self):
        """刷新 UI"""
        self._refresh_providers_list()
        self._refresh_tools_list()
    
    def _refresh_providers_list(self):
        """刷新提供商列表"""
        if not HAS_PROVIDERS:
            return
        for item in self.provider_tree.get_children():
            self.provider_tree.delete(item)
        
        configs = self.config_manager.provider_configs or []
        for config in configs:
            provider_name = PROVIDER_DISPLAY_NAMES.get(config.provider, config.provider.value) if hasattr(config.provider, 'value') else str(config.provider)
            status = "✅" if config.enabled else "❌"
            self.provider_tree.insert("", tk.END, values=(
                config.priority,
                config.name,
                provider_name,
                status
            ))
    
    def _refresh_tools_list(self):
        """刷新工具列表"""
        from .tools import get_tools
        
        for item in self.tools_tree.get_children():
            self.tools_tree.delete(item)
        
        enabled_names = [s.name for s in self.config_manager.get_enabled_skills()]
        all_tools = get_tools()
        
        for tool in all_tools:
            enabled = tool.name in enabled_names
            self.tools_tree.insert("", tk.END, values=(
                tool.name,
                tool.description,
                "✅" if enabled else "❌"
            ))
    
    def _on_provider_select(self, event):
        """选中提供商时显示详情"""
        selection = self.provider_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.provider_tree.item(item, "values")
        name = values[1]
        
        # 找到对应的配置
        configs = self.config_manager.provider_configs or []
        config = next((c for c in configs if c.name == name), None)
        
        if config:
            self._show_provider_details(config)
    
    def _show_provider_details(self, config: any):
        """显示提供商详情"""
        if not HAS_PROVIDERS:
            return
        self.detail_text.delete(1.0, tk.END)
        
        provider_name = PROVIDER_DISPLAY_NAMES.get(config.provider, config.provider.value) if hasattr(config.provider, 'value') else str(config.provider)
        model_info = config.model_info if hasattr(config, 'model_info') else None
        
        details = f"""
📋 {config.name}
{'=' * 50}

📦 提供商: {provider_name}
🔑 API Key: {'•' * (len(config.api_key) if config.api_key else 0) or '(未设置)'}
🌐 Base URL: {config.base_url or '(默认)'}
🤖 模型: {config.model}

⚙️ 配置:
   • 温度: {config.temperature}
   • 最大 Token: {config.max_tokens}
   • 超时: {getattr(config, 'timeout', 60)}秒
   • 优先级: {config.priority}
   • 状态: {'✅ 已启用' if config.enabled else '❌ 已禁用'}
"""
        if model_info:
            details += f"""
📊 模型信息:
   • 最大 Token: {model_info.max_tokens}
   • 上下文窗口: {model_info.context_window}
   • 支持工具调用: {'✅' if model_info.supports_tools else '❌'}
   • 推理模型: {'✅' if model_info.is_reasoning_model else '❌'}
   • 输入价格: ${model_info.pricing_input}/1M tokens
   • 输出价格: ${model_info.pricing_output}/1M tokens
"""
        self.detail_text.insert(1.0, details)
    
    def _add_provider(self):
        """添加提供商"""
        dialog = ProviderConfigDialog(self.window)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.config_manager.add_provider_config(dialog.result)
            self._refresh_providers_list()
    
    def _quick_add_provider(self, provider: any):
        """快捷添加提供商"""
        if not HAS_PROVIDERS:
            return
        dialog = ProviderConfigDialog(self.window)
        
        # 预填充提供商
        display_name = PROVIDER_DISPLAY_NAMES.get(provider, provider.value) if hasattr(provider, 'value') else str(provider)
        dialog.provider_var.set(display_name)
        dialog._on_provider_changed(None)
        dialog.name_var.set(f"{display_name} 配置")
        
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.config_manager.add_provider_config(dialog.result)
            self._refresh_providers_list()
    
    def _edit_provider(self):
        """编辑提供商"""
        selection = self.provider_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要编辑的提供商")
            return
        
        item = selection[0]
        values = self.provider_tree.item(item, "values")
        name = values[1]
        
        configs = self.config_manager.provider_configs or []
        config = next((c for c in configs if c.name == name), None)
        if not config:
            return
        
        dialog = ProviderConfigDialog(self.window, config)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            # 更新配置
            for i, c in enumerate(configs):
                if c.name == name:
                    configs[i] = dialog.result
                    break
            self.config_manager.provider_configs = configs
            self.config_manager._save_provider_configs()
            self._refresh_providers_list()
    
    def _delete_provider(self):
        """删除提供商"""
        selection = self.provider_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请选择要删除的提供商")
            return
        
        item = selection[0]
        values = self.provider_tree.item(item, "values")
        name = values[1]
        
        if messagebox.askyesno("确认", f"确定要删除提供商 '{name}' 吗？"):
            configs = self.config_manager.provider_configs or []
            configs = [c for c in configs if c.name != name]
            self.config_manager.provider_configs = configs
            self.config_manager._save_provider_configs()
            self._refresh_providers_list()
            self.detail_text.delete(1.0, tk.END)
    
    def _enable_selected_tool(self):
        """启用选中工具"""
        for item in self.tools_tree.selection():
            values = self.tools_tree.item(item, "values")
            tool_name = values[0]
            self.config_manager.update_skill_config(tool_name, enabled=True)
        self._refresh_tools_list()
    
    def _disable_selected_tool(self):
        """禁用选中工具"""
        for item in self.tools_tree.selection():
            values = self.tools_tree.item(item, "values")
            tool_name = values[0]
            self.config_manager.update_skill_config(tool_name, enabled=False)
        self._refresh_tools_list()
    
    def _enable_all_tools(self):
        """启用所有工具"""
        from .tools import get_tools
        for tool in get_tools():
            self.config_manager.update_skill_config(tool.name, enabled=True)
        self._refresh_tools_list()
    
    def _export_config(self):
        """导出配置"""
        file_path = filedialog.asksaveasfilename(
            title="导出配置",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if file_path:
            self.config_manager.export_config(Path(file_path))
            messagebox.showinfo("成功", "配置已导出")
    
    def _import_config(self):
        """导入配置"""
        file_path = filedialog.askopenfilename(
            title="导入配置",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                self.config_manager.import_config(Path(file_path))
                self._refresh_ui()
                messagebox.showinfo("成功", "配置已导入")
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {e}")
    
    def _test_config(self):
        """测试配置"""
        messagebox.showinfo("提示", "配置测试功能即将推出！\n\n当前配置已保存，可以在 Agent 中使用。")
    
    def _save_and_close(self):
        """保存并关闭"""
        self.config_manager._save_provider_configs()
        self.window.destroy()


def show_enhanced_config_dialog(parent):
    """显示增强版配置对话框"""
    try:
        dialog = EnhancedAgentConfigDialog(parent)
        if hasattr(dialog, 'window'):
            parent.wait_window(dialog.window)
    except Exception as e:
        messagebox.showerror("错误", f"配置界面初始化失败: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    show_enhanced_config_dialog(root)
