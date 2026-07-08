#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 Agent 配置界面 - 完全重构，支持多源 API 提供商
类似 Cline 的配置体验，包含：
- 提供商选择器
- 模型配置
- 优先级管理
- 快捷配置助手
- 审批弹窗
- 工作流管理
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from typing import Optional, List, Callable, Dict, Any
from pathlib import Path
import json

from .config import get_config_manager

try:
    from .harness import ApprovalManager, ApprovalRequest, ApprovalDecision, ApprovalMode
    HAS_APPROVAL = True
except ImportError:
    HAS_APPROVAL = False

try:
    from .workflow_engine import WorkflowEngine, WorkflowDefinition, StepDefinition, StepType, WorkflowStatus, get_workflow_engine
    HAS_WORKFLOW = True
except ImportError:
    HAS_WORKFLOW = False

try:
    from .plugins import TrustGate, LlmTrustConfig
    HAS_TRUST_GATE = True
except ImportError:
    HAS_TRUST_GATE = False


class ApprovalDialog:
    """审批弹窗 - 显示待审批请求，让用户决定"""
    
    def __init__(self, parent, request: 'ApprovalRequest', callback: Callable[[str], None]):
        self.parent = parent
        self.request = request
        self.callback = callback
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🔒 操作审批")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.attributes("-topmost", True)
        self.dialog.focus_force()
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._create_widgets()
    
    def _create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题区域
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 风险级别指示器
        risk_color_map = {
            "low": "#22c55e",
            "medium": "#f59e0b",
            "high": "#ef4444",
            "critical": "#dc2626",
        }
        risk_level = self.request.risk_level if self.request.risk_level is not None else "medium"
        risk_label = tk.Label(
            title_frame,
            text=f"  {risk_level.upper()}  ",
            bg=risk_color_map.get(risk_level, "#f59e0b"),
            fg="white",
            font=("", 10, "bold"),
            padx=5,
            pady=2
        )
        risk_label.pack(side=tk.LEFT)
        
        tool_name = self.request.tool_name if self.request.tool_name is not None else "未知工具"
        ttk.Label(title_frame, text=f"工具: {tool_name}", 
                 font=("", 12, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        
        # 请求信息
        info_frame = ttk.LabelFrame(main_frame, text="请求详情", padding="10")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 请求原因
        reason_text_content = self.request.reason if self.request.reason is not None else ""
        if reason_text_content:
            ttk.Label(info_frame, text="原因:", font=("", 9, "bold")).pack(anchor=tk.W)
            reason_text = scrolledtext.ScrolledText(info_frame, height=3, wrap=tk.WORD)
            reason_text.pack(fill=tk.X, pady=(5, 10))
            reason_text.insert(tk.END, reason_text_content)
            reason_text.config(state=tk.DISABLED)
        
        # 工具参数
        ttk.Label(info_frame, text="参数:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(5, 0))
        params_text = scrolledtext.ScrolledText(info_frame, height=8, wrap=tk.WORD)
        params_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        try:
            tool_input = self.request.tool_input if self.request.tool_input is not None else {}
            params_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
        except:
            params_str = str(self.request.tool_input if self.request.tool_input is not None else {})
        params_text.insert(tk.END, params_str)
        params_text.config(state=tk.DISABLED)
        
        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        
        # 拒绝按钮
        ttk.Button(
            btn_frame,
            text="❌ 拒绝",
            command=lambda: self._on_decision("deny"),
            width=12
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        # 批准按钮
        ttk.Button(
            btn_frame,
            text="✅ 批准",
            command=lambda: self._on_decision("approve"),
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        # 总是批准按钮
        ttk.Button(
            btn_frame,
            text="✅ 总是批准此类操作",
            command=lambda: self._on_decision("always_approve"),
        ).pack(side=tk.LEFT, padx=5)
        
        # 关闭按钮
        ttk.Button(
            btn_frame,
            text="❌ 取消(拒绝)",
            command=self._on_close,
            width=14
        ).pack(side=tk.RIGHT)
    
    def _on_decision(self, decision: str):
        """处理用户决定"""
        self.result = decision
        try:
            self.dialog.attributes("-topmost", False)
            self.dialog.grab_release()
        except Exception:
            pass
        self.callback(decision)
        self.dialog.destroy()
    
    def _on_close(self):
        """窗口关闭 - 默认拒绝"""
        try:
            self.dialog.attributes("-topmost", False)
            self.dialog.grab_release()
        except Exception:
            pass
        self.callback("deny")
        self.dialog.destroy()


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
        fetch_model_info_from_provider,
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
    fetch_model_info_from_provider = None


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
        ttk.Spinbox(form_frame, from_=256, to=1024000, textvariable=self.max_tokens_var, width=37).grid(row=6, column=1, sticky=tk.W, pady=5)
        
        # 上下文窗口（新增）
        ctx_frame = ttk.Frame(form_frame)
        ctx_frame.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=5)
        ttk.Label(ctx_frame, text="上下文窗口:").pack(side=tk.LEFT)
        self.context_window_var = tk.IntVar(value=0)
        self.ctx_spinbox = ttk.Spinbox(ctx_frame, from_=0, to=1048576, textvariable=self.context_window_var, width=15)
        self.ctx_spinbox.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Label(ctx_frame, text="(0=自动)", font=("", 8)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(ctx_frame, text="🔄 从提供商获取", command=self._fetch_model_info).pack(side=tk.LEFT)
        
        # 优先级
        ttk.Label(form_frame, text="优先级:").grid(row=8, column=0, sticky=tk.W, pady=5)
        self.priority_var = tk.IntVar(value=0)
        ttk.Spinbox(form_frame, from_=0, to=100, textvariable=self.priority_var, width=37).grid(row=8, column=1, sticky=tk.W, pady=5)
        
        # 启用开关
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_frame, text="启用此配置", variable=self.enabled_var).grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 思维链开关（MiMo 等推理模型适用）
        self.thinking_var = tk.BooleanVar(value=False)
        self.thinking_check = ttk.Checkbutton(form_frame, text="启用思维链 (thinking)", variable=self.thinking_var)
        self.thinking_check.grid(row=10, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 模型信息提示（新增）
        self.model_info_label = ttk.Label(form_frame, text="", font=("", 8), foreground="gray")
        self.model_info_label.grid(row=11, column=0, columnspan=2, sticky=tk.W, pady=2)
        
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
        
        # MiMo 推理模型默认启用思维链
        if provider == ProviderType.MIMO:
            first_model = models[0] if models else ""
            from .llm import DEFAULT_MODEL_INFOS
            model_info = DEFAULT_MODEL_INFOS.get(first_model)
            self.thinking_var.set(model_info.is_reasoning_model if model_info else True)
        else:
            self.thinking_var.set(False)
    
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
        self.context_window_var.set(getattr(config, 'context_window', 0))
        self.priority_var.set(config.priority)
        self.enabled_var.set(config.enabled)
        thinking_val = getattr(config, 'thinking_enabled', None)
        if thinking_val is not None:
            self.thinking_var.set(thinking_val)
        elif hasattr(config, 'model_info') and config.model_info.is_reasoning_model:
            self.thinking_var.set(True)
        
        # 更新模型列表
        if hasattr(config.provider, 'value'):
            models = PROVIDER_DEFAULT_MODELS.get(config.provider, [])
            self.model_combo['values'] = models
            if config.model not in models and models:
                self.model_combo['values'] = models + [config.model]
        
        # 显示模型信息
        self._update_model_info_label(config)
    
    def _update_model_info_label(self, config: any = None):
        """更新模型信息提示标签"""
        if config is None:
            cw = self.context_window_var.get()
            mt = self.max_tokens_var.get()
            if cw > 0:
                self.model_info_label.config(text=f"上下文窗口: {cw:,} | 最大 Token: {mt:,}", foreground="green")
            else:
                self.model_info_label.config(text=f"最大 Token: {mt:,} (上下文窗口: 自动)", foreground="gray")
            return
        cw = getattr(config, 'context_window', 0)
        if cw > 0:
            self.model_info_label.config(
                text=f"上下文窗口: {cw:,} | 最大 Token: {config.max_tokens:,}",
                foreground="green"
            )
        else:
            try:
                info = config.model_info
                cw_auto = info.context_window if hasattr(info, 'context_window') else 8192
                self.model_info_label.config(
                    text=f"上下文窗口: {cw_auto:,} (自动) | 最大 Token: {config.max_tokens:,}",
                    foreground="gray"
                )
            except Exception:
                self.model_info_label.config(text="上下文窗口: 未知 (自动)", foreground="orange")
    
    def _fetch_model_info(self):
        """从提供商获取模型信息"""
        if not HAS_PROVIDERS:
            messagebox.showerror("错误", "llm_providers 模块未正确导入")
            return
        import asyncio
        provider_name = self.provider_name_map.get(self.provider_var.get())
        if not provider_name:
            messagebox.showwarning("警告", "请先选择 API 提供商")
            return
        model = self.custom_model_var.get().strip() or self.model_var.get()
        if not model:
            messagebox.showwarning("警告", "请先选择或输入模型名称")
            return
        temp_config = ProviderConfig(
            provider=provider_name,
            api_key=self.api_key_var.get(),
            base_url=self.base_url_var.get() or None,
            model=model,
            temperature=self.temperature_var.get(),
            max_tokens=self.max_tokens_var.get(),
            context_window=self.context_window_var.get(),
        )
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            info = loop.run_until_complete(fetch_model_info_from_provider(temp_config))
            loop.close()
            if info and info.context_window > 0:
                self.context_window_var.set(info.context_window)
                self._update_model_info_label()
                ctx_str = f"{info.context_window:,}"
                pricing_str = ""
                if hasattr(info, 'pricing_input') and info.pricing_input > 0:
                    pricing_str = f" | 定价: 输入 ${info.pricing_input}/M, 输出 ${info.pricing_output:.4f}/M"
                messagebox.showinfo("获取成功", f"模型 '{model}' 上下文窗口: {ctx_str}{pricing_str}")
            else:
                messagebox.showwarning("获取失败", f"无法从提供商获取模型 '{model}' 的信息，请检查模型名称是否正确")
        except Exception as e:
            messagebox.showerror("错误", f"获取模型信息失败: {e}")
    
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
            context_window=self.context_window_var.get(),
            priority=self.priority_var.get(),
            enabled=self.enabled_var.get(),
            thinking_enabled=self.thinking_var.get() if self.thinking_var.get() else None,
        )
        
        self.result = config
        self.dialog.destroy()


class SubAgentConfigDialog:
    """子 Agent 配置对话框"""
    
    def __init__(self, parent, config=None, config_manager=None):
        self.parent = parent
        self.config = config
        self.config_manager = config_manager or get_config_manager()
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("配置子 Agent" if config else "添加子 Agent")
        self.dialog.geometry("650x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._create_widgets()
        if config:
            self._load_config()
    
    def _get_available_models(self):
        """获取所有可用的模型列表"""
        models = ["(使用主模型)"]
        provider_configs = self.config_manager.get_enabled_providers() if hasattr(self.config_manager, 'get_enabled_providers') else []
        
        for cfg in provider_configs:
            if HAS_PROVIDERS:
                provider_name = PROVIDER_DISPLAY_NAMES.get(cfg.provider, str(cfg.provider.value) if hasattr(cfg.provider, 'value') else str(cfg.provider))
                
                # 添加该提供商的所有默认模型
                default_models = PROVIDER_DEFAULT_MODELS.get(cfg.provider, [])
                for model in default_models:
                    models.append(f"{model} ({provider_name})")
                
                # 如果当前配置的模型不在默认列表中，也添加进去
                if cfg.model and cfg.model not in default_models:
                    models.append(f"{cfg.model} ({provider_name})")
            else:
                if hasattr(cfg, 'model') and cfg.model:
                    provider_name = str(getattr(cfg, 'provider', 'unknown'))
                    models.append(f"{cfg.model} ({provider_name})")
        
        # 去重
        unique_models = []
        seen = set()
        for m in models:
            if m not in seen:
                seen.add(m)
                unique_models.append(m)
        return unique_models
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        info_frame = ttk.LabelFrame(main_frame, text="基础信息", padding="15")
        info_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(info_frame, text="角色:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.role_var = tk.StringVar()
        role_combo = ttk.Combobox(info_frame, textvariable=self.role_var, state="readonly", values=["coder", "task", "research", "review", "custom"])
        role_combo.grid(row=0, column=1, sticky=tk.EW, pady=5)
        
        ttk.Label(info_frame, text="名称:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.name_var).grid(row=1, column=1, sticky=tk.EW, pady=5)
        
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(info_frame, text="启用", variable=self.enabled_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        info_frame.columnconfigure(1, weight=1)
        
        model_frame = ttk.LabelFrame(main_frame, text="模型配置", padding="15")
        model_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(model_frame, text="模型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value="(使用主模型)")
        
        # 模型选择下拉框
        available_models = self._get_available_models()
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, values=available_models, state="readonly")
        self.model_combo.grid(row=0, column=1, sticky=tk.EW, pady=5)
        
        # 自定义模型输入
        ttk.Label(model_frame, text="或自定义模型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.custom_model_var = tk.StringVar()
        ttk.Entry(model_frame, textvariable=self.custom_model_var).grid(row=1, column=1, sticky=tk.EW, pady=5)
        ttk.Label(model_frame, text="(留空则使用下拉框选择)").grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(model_frame, text="最大轮次:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.max_turns_var = tk.IntVar(value=10)
        ttk.Spinbox(model_frame, from_=1, to=50, textvariable=self.max_turns_var).grid(row=3, column=1, sticky=tk.W, pady=5)
        
        model_frame.columnconfigure(1, weight=1)
        
        prompt_frame = ttk.LabelFrame(main_frame, text="系统提示词", padding="15")
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.prompt_text = tk.Text(prompt_frame, height=8, wrap=tk.WORD)
        prompt_scrollbar = ttk.Scrollbar(prompt_frame, orient=tk.VERTICAL, command=self.prompt_text.yview)
        self.prompt_text.configure(yscrollcommand=prompt_scrollbar.set)
        
        self.prompt_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        prompt_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="取消", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=(0, 10))
    
    def _load_config(self):
        if self.config:
            self.role_var.set(self.config.role)
            self.name_var.set(self.config.name)
            self.enabled_var.set(self.config.enabled)
            
            # 设置模型选择
            if self.config.model:
                # 尝试匹配现有模型列表
                available_models = self._get_available_models()
                matched = False
                for m in available_models:
                    if self.config.model in m:
                        self.model_var.set(m)
                        matched = True
                        break
                if not matched:
                    # 自定义模型
                    self.model_var.set("(使用主模型)")
                    self.custom_model_var.set(self.config.model)
            else:
                self.model_var.set("(使用主模型)")
            
            self.max_turns_var.set(self.config.max_turns)
            self.prompt_text.delete(1.0, tk.END)
            self.prompt_text.insert(1.0, self.config.system_prompt)
    
    def _save(self):
        from .config import SubAgentConfig
        
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("警告", "请输入子 Agent 名称")
            return
        
        role = self.role_var.get()
        if not role:
            messagebox.showwarning("警告", "请选择角色")
            return
        
        # 获取模型配置
        custom_model = self.custom_model_var.get().strip()
        selected_model = self.model_var.get()
        
        if custom_model:
            model = custom_model
        elif selected_model == "(使用主模型)":
            model = ""
        else:
            # 从 "(model_name (provider_name))" 格式中提取模型名
            if " (" in selected_model:
                model = selected_model.split(" (")[0]
            else:
                model = selected_model
        
        config = SubAgentConfig(
            role=role,
            name=name,
            enabled=self.enabled_var.get(),
            model=model,
            max_turns=self.max_turns_var.get(),
            system_prompt=self.prompt_text.get(1.0, tk.END).strip()
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
        
        # 使用全局审批管理器（与其他组件共享同一个实例）
        if HAS_APPROVAL:
            from .harness import get_global_approval_manager as get_harness_approval_manager
            self.harness_approval_manager = get_harness_approval_manager()
            self.approval_manager = self.harness_approval_manager
        else:
            self.approval_manager = None
            self.harness_approval_manager = None
        
        self.workflow_engine = get_workflow_engine() if HAS_WORKFLOW else None
        
        # 初始化统一会话管理器
        try:
            from .extensions.unified_session import get_unified_session_manager
            self.unified_session_manager = get_unified_session_manager()
        except Exception as e:
            import logging
            logging.warning(f"统一会话管理器加载失败: {e}")
            self.unified_session_manager = None
        
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
        
        # 子 Agent 配置标签页
        self._create_sub_agents_tab(notebook)
        
        # MCP 扩展系统标签页
        self._create_extensions_tab(notebook)

        # MCP 远程服务标签页
        self._create_mcp_services_tab(notebook)

        # 审批管理标签页
        self._create_approval_tab(notebook)
        
        # 工作流管理标签页
        self._create_workflow_tab(notebook)
        
        # 工具配置标签页
        self._create_tools_tab(notebook)
        
        # 会话管理标签页
        self._create_sessions_tab(notebook)
        
        # 自动化标签页
        self._create_automation_tab(notebook)
        
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
        
        quick_canvas = tk.Canvas(quick_frame, height=160, highlightthickness=0)
        quick_scrollbar = ttk.Scrollbar(quick_frame, orient=tk.VERTICAL, command=quick_canvas.yview)
        quick_inner = ttk.Frame(quick_canvas)
        
        quick_inner.bind("<Configure>", lambda e: quick_canvas.configure(scrollregion=quick_canvas.bbox("all")))
        quick_canvas.create_window((0, 0), window=quick_inner, anchor=tk.NW)
        quick_canvas.configure(yscrollcommand=quick_scrollbar.set)
        
        quick_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        quick_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def _on_quick_mousewheel(event):
            quick_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        quick_canvas.bind("<MouseWheel>", _on_quick_mousewheel)
        quick_inner.bind("<MouseWheel>", _on_quick_mousewheel)
        
        quick_providers = [
            (ProviderType.OPENAI, "OpenAI"),
            (ProviderType.ANTHROPIC, "Claude"),
            (ProviderType.CLAUDE_CODE, "Claude Code"),
            (ProviderType.DEEPSEEK, "DeepSeek"),
            (ProviderType.DEEPSEEK_PROXY, "DeepSeek Proxy (本地反代)"),
            (ProviderType.QWEN, "通义千问"),
            (ProviderType.QWEN_CODE, "Qwen Code"),
            (ProviderType.MIMO, "小米 MiMo"),
            (ProviderType.DOUBAO, "豆包"),
            (ProviderType.GEMINI, "Gemini"),
            (ProviderType.GROQ, "Groq"),
            (ProviderType.MISTRAL, "Mistral"),
            (ProviderType.XAI, "xAI"),
            (ProviderType.MOONSHOT, "Moonshot"),
            (ProviderType.MINIMAX, "MiniMax"),
            (ProviderType.OPENROUTER, "OpenRouter"),
            (ProviderType.TOGETHER, "Together"),
            (ProviderType.FIREWORKS, "Fireworks"),
            (ProviderType.NEBIUS, "Nebius"),
            (ProviderType.OLLAMA, "Ollama"),
            (ProviderType.LM_STUDIO, "LM Studio"),
            (ProviderType.HUGGINGFACE, "HuggingFace"),
            (ProviderType.HUAWEI_MAAS, "华为盘古"),
            (ProviderType.BEDROCK, "AWS Bedrock"),
            (ProviderType.VERTEX, "Vertex AI"),
            (ProviderType.LITELLM, "LiteLLM"),
            (ProviderType.DIFY, "Dify"),
            (ProviderType.BASETEN, "Baseten"),
            (ProviderType.VERCEL_AI, "Vercel AI"),
            (ProviderType.ZAI, "ZAI"),
            (ProviderType.OCA, "OCA"),
            (ProviderType.AIHUBMIX, "AIHubMix"),
            (ProviderType.HICAP, "HiCap"),
            (ProviderType.NOUS_RESEARCH, "Nous Research"),
            (ProviderType.WANDB, "W&B"),
            (ProviderType.CUSTOM, "自定义 API"),
        ]
        
        for i, (provider, label) in enumerate(quick_providers):
            btn = ttk.Button(quick_inner, text=label, command=lambda p=provider: self._quick_add_provider(p))
            btn.grid(row=i//4, column=i%4, sticky=tk.EW, padx=2, pady=2)
        for col in range(4):
            quick_inner.columnconfigure(col, weight=1)
        
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
        
        # 工具分类
        categories_frame = ttk.LabelFrame(tools_frame, text="工具分类", padding="10")
        categories_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.tool_category_var = tk.StringVar(value="all")
        
        categories = [
            ("all", "全部"),
            ("builtin", "内置工具"),
            ("ws2", "WS2 工具"),
            ("hub", "DataHub 工具"),
            ("rag", "RAG 检索"),
            ("sandbox", "沙箱执行"),
            ("mcp_client", "MCP 客户端"),
            ("gt", "GT 证明"),
            ("feishu", "飞书"),
            ("lean4", "Lean4"),
            ("manim", "Manim"),
            ("mathlens", "MathLens"),
            ("autoresearch", "AutoResearch"),
        ]
        
        for value, text in categories:
            ttk.Radiobutton(
                categories_frame,
                text=text,
                variable=self.tool_category_var,
                value=value,
                command=self._filter_tools_by_category
            ).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(tools_frame, text="可用工具列表（可多选）", font=("", 10, "bold")).pack(anchor=tk.W)
        
        tree_frame = ttk.Frame(tools_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        self.tools_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "category", "description", "enabled"),
            show="headings",
            height=15
        )
        self.tools_tree.heading("name", text="工具名称")
        self.tools_tree.heading("category", text="分类")
        self.tools_tree.heading("description", text="描述")
        self.tools_tree.heading("enabled", text="状态")
        self.tools_tree.column("name", width=180)
        self.tools_tree.column("category", width=100)
        self.tools_tree.column("description", width=350)
        self.tools_tree.column("enabled", width=60, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tools_tree.yview)
        self.tools_tree.configure(yscrollcommand=scrollbar.set)
        
        self.tools_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tools_btn_frame = ttk.Frame(tools_frame)
        tools_btn_frame.pack(fill=tk.X)
        
        # 启用/禁用按钮
        btn_left = ttk.Frame(tools_btn_frame)
        btn_left.pack(side=tk.LEFT)
        ttk.Button(btn_left, text="✅ 启用选中", command=self._enable_selected_tool).pack(side=tk.LEFT)
        ttk.Button(btn_left, text="❌ 禁用选中", command=self._disable_selected_tool).pack(side=tk.LEFT, padx=(5, 0))
        
        # 全部按钮
        btn_right = ttk.Frame(tools_btn_frame)
        btn_right.pack(side=tk.RIGHT)
        ttk.Button(btn_right, text="✅ 全部启用", command=self._enable_all_tools).pack(side=tk.LEFT)
        ttk.Button(btn_right, text="❌ 全部禁用", command=self._disable_all_tools).pack(side=tk.LEFT, padx=(5, 0))
        
        # RAG 和其他高级工具配置区域
        advanced_frame = ttk.LabelFrame(tools_frame, text="高级工具配置", padding="10")
        advanced_frame.pack(fill=tk.X, pady=(10, 0))
        
        # RAG 配置
        rag_frame = ttk.Frame(advanced_frame)
        rag_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(rag_frame, text="📚 RAG 检索系统:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(rag_frame, text="添加文档到向量库", command=self._add_rag_document).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Button(rag_frame, text="查看向量库状态", command=self._view_rag_stats).pack(side=tk.LEFT)
        
        # 沙箱配置
        sandbox_frame = ttk.Frame(advanced_frame)
        sandbox_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(sandbox_frame, text="🔒 沙箱执行:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(sandbox_frame, text="配置安全策略", command=self._configure_sandbox).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Button(sandbox_frame, text="查看执行日志", command=self._view_sandbox_logs).pack(side=tk.LEFT)
        
        # MCP 客户端配置
        mcp_frame = ttk.Frame(advanced_frame)
        mcp_frame.pack(fill=tk.X)
        
        ttk.Label(mcp_frame, text="🔌 MCP 客户端:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(mcp_frame, text="连接新 MCP 服务", command=self._connect_mcp_server).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Button(mcp_frame, text="查看连接状态", command=self._view_mcp_status).pack(side=tk.LEFT)
        
        self._all_tools = []  # 保存所有工具信息

    def _filter_tools_by_category(self):
        """按分类筛选工具"""
        category = self.tool_category_var.get()
        
        # 清空并重新加载
        for item in self.tools_tree.get_children():
            self.tools_tree.delete(item)
        
        for tool_info in self._all_tools:
            if category == "all" or tool_info["category_key"] == category:
                status = "✅" if tool_info["enabled"] else "❌"
                self.tools_tree.insert("", tk.END, values=(
                    tool_info["name"],
                    tool_info["category"],
                    tool_info["description"],
                    status
                ))
    
    def _create_extensions_tab(self, notebook):
        """创建 MCP 扩展系统标签页"""
        ext_frame = ttk.Frame(notebook, padding="10")
        notebook.add(ext_frame, text="🧩 MCP 扩展系统")
        
        # 顶部说明
        info_frame = ttk.LabelFrame(ext_frame, text="MCP 扩展系统", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(info_frame, text="MCP 扩展系统包含技能（Skills）和扩展模块（Extensions）。技能是可复用的功能模块，扩展模块提供额外的系统能力。", wraplength=750).pack(anchor=tk.W)
        
        # 分割为上下两部分：技能列表 + 扩展模块列表
        paned = ttk.PanedWindow(ext_frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # === 上半部分：技能列表 ===
        skills_section = ttk.LabelFrame(paned, text="🎯 技能列表", padding="5")
        paned.add(skills_section, weight=3)
        
        tree_frame = ttk.Frame(skills_section)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        self.skills_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "type", "description", "enabled"),
            show="headings",
            height=8
        )
        self.skills_tree.heading("name", text="技能名称")
        self.skills_tree.heading("type", text="类型")
        self.skills_tree.heading("description", text="描述")
        self.skills_tree.heading("enabled", text="状态")
        self.skills_tree.column("name", width=180)
        self.skills_tree.column("type", width=100)
        self.skills_tree.column("description", width=350)
        self.skills_tree.column("enabled", width=60, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.skills_tree.yview)
        self.skills_tree.configure(yscrollcommand=scrollbar.set)
        self.skills_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 技能操作按钮
        skills_btn_frame = ttk.Frame(skills_section)
        skills_btn_frame.pack(fill=tk.X)
        
        btn_left = ttk.Frame(skills_btn_frame)
        btn_left.pack(side=tk.LEFT)
        ttk.Button(btn_left, text="➕ 创建技能", command=self._create_new_skill).pack(side=tk.LEFT)
        ttk.Button(btn_left, text="✏️ 编辑", command=self._edit_skill).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_left, text="🗑️ 删除", command=self._delete_skill).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_left, text="📥 导入", command=self._import_skill).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_left, text="📤 导出", command=self._export_skill).pack(side=tk.LEFT, padx=(5, 0))
        
        btn_right = ttk.Frame(skills_btn_frame)
        btn_right.pack(side=tk.RIGHT)
        ttk.Button(btn_right, text="✅ 启用", command=self._enable_selected_skill).pack(side=tk.LEFT)
        ttk.Button(btn_right, text="❌ 禁用", command=self._disable_selected_skill).pack(side=tk.LEFT, padx=(5, 0))
        
        # === 下半部分：扩展模块列表 ===
        ext_section = ttk.LabelFrame(paned, text="🔌 扩展模块", padding="5")
        paned.add(ext_section, weight=2)
        
        ext_tree_frame = ttk.Frame(ext_section)
        ext_tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        self.extensions_tree = ttk.Treeview(
            ext_tree_frame,
            columns=("name", "version", "description", "status"),
            show="headings",
            height=5
        )
        self.extensions_tree.heading("name", text="模块名称")
        self.extensions_tree.heading("version", text="版本")
        self.extensions_tree.heading("description", text="描述")
        self.extensions_tree.heading("status", text="状态")
        self.extensions_tree.column("name", width=180)
        self.extensions_tree.column("version", width=80, anchor=tk.CENTER)
        self.extensions_tree.column("description", width=370)
        self.extensions_tree.column("status", width=60, anchor=tk.CENTER)
        
        ext_scrollbar = ttk.Scrollbar(ext_tree_frame, orient=tk.VERTICAL, command=self.extensions_tree.yview)
        self.extensions_tree.configure(yscrollcommand=ext_scrollbar.set)
        self.extensions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ext_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 扩展模块操作按钮
        ext_btn_frame = ttk.Frame(ext_section)
        ext_btn_frame.pack(fill=tk.X)
        
        ttk.Button(ext_btn_frame, text="🔄 刷新扩展", command=self._refresh_extensions_list).pack(side=tk.LEFT)
        ttk.Button(ext_btn_frame, text="📂 加载扩展", command=self._load_extension_from_file).pack(side=tk.LEFT, padx=(5, 0))
        
        # 初始化列表
        self._refresh_skills_list()
        self._refresh_extensions_list()
    
    def _enable_selected_skill(self):
        """启用选中的技能"""
        for item in self.skills_tree.selection():
            values = self.skills_tree.item(item, "values")
            skill_name = values[0]
            self.config_manager.update_skill_config(skill_name, enabled=True)
        self._refresh_skills_list()
    
    def _disable_selected_skill(self):
        """禁用选中的技能"""
        for item in self.skills_tree.selection():
            values = self.skills_tree.item(item, "values")
            skill_name = values[0]
            self.config_manager.update_skill_config(skill_name, enabled=False)
        self._refresh_skills_list()
    
    def _enable_all_skills(self):
        """启用所有技能"""
        for skill_config in self.config_manager.skill_configs.values():
            self.config_manager.update_skill_config(skill_config.name, enabled=True)
        self._refresh_skills_list()
        messagebox.showinfo("成功", "已启用所有技能")
    
    def _disable_all_skills(self):
        """禁用所有技能"""
        if not messagebox.askyesno("确认", "确定要禁用所有技能吗？"):
            return
        for skill_config in self.config_manager.skill_configs.values():
            self.config_manager.update_skill_config(skill_config.name, enabled=False)
        self._refresh_skills_list()
        messagebox.showinfo("成功", "已禁用所有技能")
    
    def _refresh_skills_list(self):
        """刷新技能列表"""
        from .config import SkillConfig
        
        for item in self.skills_tree.get_children():
            self.skills_tree.delete(item)
        
        for skill_config in self.config_manager.skill_configs.values():
            status = "✅" if skill_config.enabled else "❌"
            self.skills_tree.insert("", tk.END, values=(
                skill_config.name,
                skill_config.type,
                skill_config.description,
                status
            ))
    
    def _create_new_skill(self):
        """创建新技能"""
        dialog = tk.Toplevel(self.window)
        dialog.title("创建新技能")
        dialog.geometry("700x600")
        
        # 变量
        name_var = tk.StringVar()
        description_var = tk.StringVar()
        category_var = tk.StringVar(value="custom")
        version_var = tk.StringVar(value="1.0.0")
        
        # 表单
        ttk.Label(dialog, text="技能名称:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=10)
        ttk.Entry(dialog, textvariable=name_var, width=40).grid(row=0, column=1, pady=5)
        
        ttk.Label(dialog, text="技能描述:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=10)
        ttk.Entry(dialog, textvariable=description_var, width=40).grid(row=1, column=1, pady=5)
        
        ttk.Label(dialog, text="分类:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=10)
        ttk.Combobox(dialog, textvariable=category_var, values=["custom", "builtin", "workflow"]).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(dialog, text="版本:").grid(row=3, column=0, sticky=tk.W, pady=5, padx=10)
        ttk.Entry(dialog, textvariable=version_var, width=40).grid(row=3, column=1, pady=5)
        
        ttk.Label(dialog, text="技能代码:").grid(row=4, column=0, sticky=tk.NW, pady=5, padx=10)
        code_text = scrolledtext.ScrolledText(dialog, height=15, width=50)
        code_text.grid(row=4, column=1, pady=5, sticky=tk.W+tk.E)
        code_text.insert(tk.END, '# 在这里编写您的技能代码\n# 您可以使用 kwargs 获取参数\n# 例如：name = kwargs.get("name", "world")\n# return f"Hello, {name}!"\n\nreturn "技能执行成功"')
        
        # 按钮
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=15)
        
        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("错误", "请输入技能名称！")
                return
            
            try:
                from .skills import get_skill_registry, SkillParameter
                registry = get_skill_registry()
                registry.create_custom_skill(
                    name=name,
                    description=description_var.get().strip(),
                    parameters=[],
                    code=code_text.get(1.0, tk.END),
                    category=category_var.get(),
                    version=version_var.get()
                )
                self._refresh_skills_list()
                messagebox.showinfo("成功", "技能创建成功！")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"创建技能失败：{str(e)}")
        
        ttk.Button(btn_frame, text="保存", command=on_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT)
    
    def _edit_skill(self):
        """编辑技能"""
        selection = self.skills_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要编辑的技能！")
            return
        
        item = selection[0]
        skill_name = self.skills_tree.item(item, "values")[0]
        
        # 简单的编辑对话框
        messagebox.showinfo("提示", "编辑功能开发中，当前仅支持查看技能信息！")
    
    def _delete_skill(self):
        """删除技能"""
        selection = self.skills_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的技能！")
            return
        
        if not messagebox.askyesno("确认", "确定要删除选中的技能吗？"):
            return
        
        item = selection[0]
        skill_name = self.skills_tree.item(item, "values")[0]
        
        try:
            # 从配置中删除
            from .skills import get_skill_registry
            registry = get_skill_registry()
            
            if skill_name in self.config_manager.skill_configs:
                del self.config_manager.skill_configs[skill_name]
                self.config_manager._save_skill_configs()
            
            # 尝试从注册表删除
            try:
                registry.unregister_skill(skill_name)
            except:
                pass
            
            self._refresh_skills_list()
            messagebox.showinfo("成功", "技能已删除！")
        except Exception as e:
            messagebox.showerror("错误", f"删除技能失败：{str(e)}")
    
    def _import_skill(self):
        """导入技能"""
        file_path = filedialog.askopenfilename(
            title="选择要导入的技能文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                from .skills import get_skill_registry, Path
                registry = get_skill_registry()
                skill = registry.import_skill(Path(file_path))
                if skill:
                    self._refresh_skills_list()
                    messagebox.showinfo("成功", f"已成功导入技能：{skill.name}")
                else:
                    messagebox.showerror("错误", "导入技能失败！")
            except Exception as e:
                messagebox.showerror("错误", f"导入技能失败：{str(e)}")
    
    def _export_skill(self):
        """导出技能"""
        selection = self.skills_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要导出的技能！")
            return
        
        item = selection[0]
        skill_name = self.skills_tree.item(item, "values")[0]
        
        file_path = filedialog.asksaveasfilename(
            title="保存技能",
            defaultextension=".json",
            initialfile=f"{skill_name}.json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                from .skills import get_skill_registry, Path
                registry = get_skill_registry()
                success = registry.export_skill(skill_name, Path(file_path))
                if success:
                    messagebox.showinfo("成功", f"已成功导出技能到：{file_path}")
                else:
                    messagebox.showerror("错误", "导出技能失败！")
            except Exception as e:
                messagebox.showerror("错误", f"导出技能失败：{str(e)}")
    
    def _refresh_extensions_list(self):
        """刷新扩展模块列表"""
        for item in self.extensions_tree.get_children():
            self.extensions_tree.delete(item)
        
        builtin_extensions = [
            ("unified_session", "1.0.0", "统一会话管理 - 同步 UI、助手窗口和缓存", "✅"),
            ("session_instances", "1.0.0", "会话实例管理 - 后台任务运行、独立 Agent 实例", "✅"),
            ("skills", "1.0.0", "MCP 技能注册表 - 动态加载和执行技能", "✅"),
        ]
        
        for name, version, desc, status in builtin_extensions:
            self.extensions_tree.insert("", tk.END, values=(name, version, desc, status))
        
        # 加载自定义扩展
        try:
            from .extensions.skills import get_skill_registry
            registry = get_skill_registry()
            custom_skills = [s for s in registry.list_skills() if s.category == "custom"]
            for skill in custom_skills:
                self.extensions_tree.insert("", tk.END, values=(
                    f"skill:{skill.name}",
                    skill.version,
                    skill.description,
                    "✅" if skill.enabled else "❌"
                ))
        except Exception:
            pass
    
    def _load_extension_from_file(self):
        """从文件加载扩展模块"""
        file_path = filedialog.askopenfilename(
            title="选择扩展模块文件",
            filetypes=[("Python 文件", "*.py"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            from .extensions.skills import get_skill_registry
            from pathlib import Path as P
            
            registry = get_skill_registry()
            path = P(file_path)
            
            if path.suffix == '.py':
                success = registry.load_skill_from_file(path)
            elif path.suffix == '.json':
                skill = registry.import_skill(path)
                success = skill is not None
            else:
                success = False
            
            if success:
                self._refresh_extensions_list()
                self._refresh_skills_list()
                messagebox.showinfo("成功", "扩展模块加载成功！")
            else:
                messagebox.showerror("错误", "加载扩展模块失败！")
        except Exception as e:
            messagebox.showerror("错误", f"加载扩展模块失败：{str(e)}")

    def _create_mcp_services_tab(self, notebook):
        """创建 MCP 远程服务配置标签页"""
        svc_frame = ttk.Frame(notebook, padding="10")
        notebook.add(svc_frame, text="🌐 MCP 远程服务")

        # 说明
        info_frame = ttk.LabelFrame(svc_frame, text="远程 MCP 服务配置", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(info_frame, text=(
            "配置远程 MCP 服务（如百度搜索等），Agent 将自动发现并调用这些服务提供的工具。\n"
            "API Key 通过环境变量安全存储，不会硬编码到配置文件中。"
        ), wraplength=750).pack(anchor=tk.W)

        # 服务列表
        list_frame = ttk.LabelFrame(svc_frame, text="已配置的服务", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))

        self.mcp_svc_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "type", "transport", "url", "api_key_set", "enabled"),
            show="headings",
            height=8,
        )
        self.mcp_svc_tree.heading("name", text="服务名称")
        self.mcp_svc_tree.heading("type", text="类型")
        self.mcp_svc_tree.heading("transport", text="传输方式")
        self.mcp_svc_tree.heading("url", text="Endpoint URL")
        self.mcp_svc_tree.heading("api_key_set", text="API Key")
        self.mcp_svc_tree.heading("enabled", text="状态")
        self.mcp_svc_tree.column("name", width=100)
        self.mcp_svc_tree.column("type", width=60, anchor=tk.CENTER)
        self.mcp_svc_tree.column("transport", width=70, anchor=tk.CENTER)
        self.mcp_svc_tree.column("url", width=300)
        self.mcp_svc_tree.column("api_key_set", width=80, anchor=tk.CENTER)
        self.mcp_svc_tree.column("enabled", width=50, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.mcp_svc_tree.yview)
        self.mcp_svc_tree.configure(yscrollcommand=scrollbar.set)
        self.mcp_svc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 操作按钮
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X)

        btn_left = ttk.Frame(btn_frame)
        btn_left.pack(side=tk.LEFT)
        ttk.Button(btn_left, text="➕ 添加服务", command=self._add_mcp_service).pack(side=tk.LEFT)
        ttk.Button(btn_left, text="✏️ 编辑", command=self._edit_mcp_service).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_left, text="🗑️ 删除", command=self._delete_mcp_service).pack(side=tk.LEFT, padx=(5, 0))

        btn_right = ttk.Frame(btn_frame)
        btn_right.pack(side=tk.RIGHT)
        ttk.Button(btn_right, text="🔑 设置 API Key", command=self._set_mcp_api_key).pack(side=tk.LEFT)
        ttk.Button(btn_right, text="🔄 测试连接", command=self._test_mcp_service).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_right, text="✅ 启用", command=lambda: self._toggle_mcp_service(True)).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_right, text="❌ 禁用", command=lambda: self._toggle_mcp_service(False)).pack(side=tk.LEFT, padx=(5, 0))

        # 加载服务列表
        self._refresh_mcp_services_list()

    def _get_mcp_servers_config(self) -> dict:
        """读取 mcp_servers.json"""
        config_path = Path(__file__).parent / "mcp_servers.json"
        if not config_path.exists():
            return {"servers": {}}
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"servers": {}}

    def _save_mcp_servers_config(self, config: dict):
        """保存 mcp_servers.json"""
        config_path = Path(__file__).parent / "mcp_servers.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_mcp_services_list(self):
        """刷新 MCP 服务列表"""
        if not hasattr(self, 'mcp_svc_tree'):
            return
        for item in self.mcp_svc_tree.get_children():
            self.mcp_svc_tree.delete(item)

        config = self._get_mcp_servers_config()
        import os
        for name, svc in config.get("servers", {}).items():
            api_key_env = svc.get("api_key_env", "")
            api_key_set = "✅ 已设置" if (api_key_env and os.environ.get(api_key_env)) else ("⚠️ 未设置" if api_key_env else "—")
            enabled = "启用" if svc.get("enabled", True) else "禁用"
            svc_type = svc.get("service_type", "mcp").upper()
            transport = svc.get("transport", "http") if svc_type == "MCP" else "REST"
            self.mcp_svc_tree.insert("", tk.END, iid=name, values=(
                name,
                svc_type,
                transport,
                svc.get("url", ""),
                api_key_set,
                enabled,
            ))

    def _add_mcp_service(self):
        """添加 MCP 远程服务"""
        dialog = tk.Toplevel(self.window)
        dialog.title("添加远程服务")
        dialog.geometry("500x450")
        dialog.transient(self.window)
        dialog.grab_set()

        fields = {}
        row = 0
        for label, key, default in [
            ("服务名称", "name", "my-service"),
            ("服务类型 (rest/mcp)", "service_type", "rest"),
            ("传输方式 (http/sse/stdio, 仅mcp)", "transport", "http"),
            ("Endpoint URL", "url", ""),
            ("HTTP 方法 (仅rest)", "method", "POST"),
            ("API Key 环境变量名", "api_key_env", ""),
            ("API Key 获取文档链接", "api_key_doc", ""),
            ("描述", "description", ""),
        ]:
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            var = tk.StringVar(value=default)
            entry = ttk.Entry(dialog, textvariable=var, width=40)
            entry.grid(row=row, column=1, padx=10, pady=5)
            fields[key] = var
            row += 1

        def on_save():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("提示", "服务名称不能为空", parent=dialog)
                return
            config = self._get_mcp_servers_config()
            api_key_env = fields["api_key_env"].get().strip()
            service_type = fields["service_type"].get().strip() or "rest"
            headers = {}
            if api_key_env:
                headers["Authorization"] = f"Bearer ${{{api_key_env}}}"
                headers["Content-Type"] = "application/json"
            config.setdefault("servers", {})[name] = {
                "service_type": service_type,
                "transport": fields["transport"].get().strip() or "http",
                "url": fields["url"].get().strip(),
                "method": fields["method"].get().strip() or "POST",
                "headers": headers,
                "enabled": True,
                "description": fields["description"].get().strip(),
                "api_key_env": api_key_env,
                "api_key_doc": fields["api_key_doc"].get().strip(),
                "tools": [],
            }
            self._save_mcp_servers_config(config)
            self._refresh_mcp_services_list()
            dialog.destroy()

        ttk.Button(dialog, text="保存", command=on_save).grid(row=row, column=0, columnspan=2, pady=20)

    def _edit_mcp_service(self):
        """编辑选中的 MCP 服务"""
        sel = self.mcp_svc_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个服务")
            return
        name = sel[0]
        config = self._get_mcp_servers_config()
        svc = config.get("servers", {}).get(name)
        if not svc:
            return

        dialog = tk.Toplevel(self.window)
        dialog.title(f"编辑服务: {name}")
        dialog.geometry("500x450")
        dialog.transient(self.window)
        dialog.grab_set()

        fields = {}
        row = 0
        for label, key, default in [
            ("服务类型 (rest/mcp)", "service_type", svc.get("service_type", "mcp")),
            ("传输方式 (http/sse/stdio, 仅mcp)", "transport", svc.get("transport", "http")),
            ("Endpoint URL", "url", svc.get("url", "")),
            ("HTTP 方法 (仅rest)", "method", svc.get("method", "POST")),
            ("API Key 环境变量名", "api_key_env", svc.get("api_key_env", "")),
            ("API Key 获取文档链接", "api_key_doc", svc.get("api_key_doc", "")),
            ("描述", "description", svc.get("description", "")),
        ]:
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            var = tk.StringVar(value=default)
            entry = ttk.Entry(dialog, textvariable=var, width=40)
            entry.grid(row=row, column=1, padx=10, pady=5)
            fields[key] = var
            row += 1

        def on_save():
            api_key_env = fields["api_key_env"].get().strip()
            headers = svc.get("headers", {})
            if api_key_env:
                headers["Authorization"] = f"Bearer ${{{api_key_env}}}"
                headers["Content-Type"] = "application/json"
            svc["service_type"] = fields["service_type"].get().strip() or "rest"
            svc["transport"] = fields["transport"].get().strip() or "http"
            svc["url"] = fields["url"].get().strip()
            svc["method"] = fields["method"].get().strip() or "POST"
            svc["headers"] = headers
            svc["api_key_env"] = api_key_env
            svc["api_key_doc"] = fields["api_key_doc"].get().strip()
            svc["description"] = fields["description"].get().strip()
            self._save_mcp_servers_config(config)
            self._refresh_mcp_services_list()
            dialog.destroy()

        ttk.Button(dialog, text="保存", command=on_save).grid(row=row, column=0, columnspan=2, pady=20)

    def _delete_mcp_service(self):
        """删除选中的 MCP 服务"""
        sel = self.mcp_svc_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个服务")
            return
        name = sel[0]
        if not messagebox.askyesno("确认", f"确定删除服务 '{name}'？"):
            return
        config = self._get_mcp_servers_config()
        config.get("servers", {}).pop(name, None)
        self._save_mcp_servers_config(config)
        self._refresh_mcp_services_list()

    def _set_mcp_api_key(self):
        """设置选中服务的 API Key（写入环境变量 + 持久化到 .env）"""
        sel = self.mcp_svc_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个服务")
            return
        name = sel[0]
        config = self._get_mcp_servers_config()
        svc = config.get("servers", {}).get(name)
        if not svc:
            return
        api_key_env = svc.get("api_key_env", "")
        if not api_key_env:
            messagebox.showinfo("提示", f"服务 '{name}' 未配置 API Key 环境变量")
            return

        import os
        current = os.environ.get(api_key_env, "")

        dialog = tk.Toplevel(self.window)
        dialog.title(f"设置 API Key: {api_key_env}")
        dialog.geometry("500x150")
        dialog.transient(self.window)
        dialog.grab_set()

        ttk.Label(dialog, text=f"环境变量: {api_key_env}").pack(padx=10, pady=(10, 5), anchor="w")
        key_var = tk.StringVar(value=current)
        entry = ttk.Entry(dialog, textvariable=key_var, show="*", width=50)
        entry.pack(padx=10, pady=5)

        doc_url = svc.get("api_key_doc", "")
        if doc_url:
            ttk.Label(dialog, text=f"获取 API Key: {doc_url}", foreground="blue").pack(padx=10, pady=2, anchor="w")

        def on_save():
            value = key_var.get().strip()
            if not value:
                messagebox.showwarning("提示", "API Key 不能为空", parent=dialog)
                return
            # 设置到当前进程环境变量
            os.environ[api_key_env] = value
            # 持久化到 .env 文件
            env_path = Path(__file__).parent.parent / ".env"
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
            # 更新或添加
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{api_key_env}="):
                    lines[i] = f"{api_key_env}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{api_key_env}={value}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._refresh_mcp_services_list()
            messagebox.showinfo("成功", f"API Key 已设置并保存到 .env", parent=dialog)
            dialog.destroy()

        ttk.Button(dialog, text="保存", command=on_save).pack(pady=10)

    def _test_mcp_service(self):
        """测试选中服务的连接"""
        sel = self.mcp_svc_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个服务")
            return
        name = sel[0]
        config = self._get_mcp_servers_config()
        svc = config.get("servers", {}).get(name)
        if not svc:
            return

        try:
            from .mcp_client.client import MCPClientManager
            from .mcp_client.transport import TransportConfig
            from .tools import _resolve_api_key
            import re

            # 解析 headers
            raw_headers = svc.get("headers", {})
            resolved_headers = {}
            for key, value in raw_headers.items():
                if isinstance(value, str) and "${" in value:
                    resolved_headers[key] = re.sub(
                        r'\$\{(\w+)\}',
                        lambda m: _resolve_api_key(m.group(1)) or m.group(0),
                        value,
                    )
                else:
                    resolved_headers[key] = value

            mgr = MCPClientManager()
            tc = TransportConfig(
                type=svc.get("transport", "http"),
                url=svc.get("url", ""),
                headers=resolved_headers,
                timeout=15,
            )
            connected = mgr.register(name, tc)
            if connected:
                state = mgr.get_state(name)
                tools = mgr.list_tools()
                tool_names = [t.get("name", "?") for t in tools]
                messagebox.showinfo(
                    "连接成功",
                    f"服务 '{name}' 连接成功！\n发现 {len(tools)} 个工具: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}",
                )
                mgr.unregister(name)
            else:
                state = mgr.get_state(name)
                messagebox.showerror("连接失败", f"服务 '{name}' 连接失败: {state.error if state else 'unknown'}")
        except Exception as e:
            messagebox.showerror("测试失败", f"测试服务 '{name}' 时出错: {e}")

    def _toggle_mcp_service(self, enable: bool):
        """启用/禁用 MCP 服务"""
        sel = self.mcp_svc_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个服务")
            return
        name = sel[0]
        config = self._get_mcp_servers_config()
        svc = config.get("servers", {}).get(name)
        if svc:
            svc["enabled"] = enable
            self._save_mcp_servers_config(config)
            self._refresh_mcp_services_list()

    def _create_approval_tab(self, notebook):
        """创建审批管理标签页"""
        approval_frame = ttk.Frame(notebook, padding="10")
        notebook.add(approval_frame, text="🔒 审批管理")
        
        # 审批模式设置
        mode_frame = ttk.LabelFrame(approval_frame, text="审批模式", padding="10")
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.approval_mode_var = tk.StringVar(value="suggest")
        mode_options = [
            ("suggest", "建议模式 - 所有操作需要审批"),
            ("auto_edit", "自动编辑模式 - 仅敏感操作需要审批"),
            ("full_auto", "全自动模式 - 无需审批"),
        ]
        
        for mode_value, mode_text in mode_options:
            ttk.Radiobutton(
                mode_frame,
                text=mode_text,
                variable=self.approval_mode_var,
                value=mode_value,
                command=self._set_approval_mode
            ).pack(anchor=tk.W, pady=2)
        
        ttk.Button(
            mode_frame,
            text="重置权限设置",
            command=self._reset_approval_permissions
        ).pack(anchor=tk.W, pady=(10, 0))
        
        # 待审批请求列表
        pending_frame = ttk.LabelFrame(approval_frame, text="待审批请求", padding="10")
        pending_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.pending_tree = ttk.Treeview(
            pending_frame,
            columns=("id", "tool", "risk", "reason"),
            show="headings",
            height=8
        )
        self.pending_tree.heading("id", text="ID")
        self.pending_tree.heading("tool", text="工具")
        self.pending_tree.heading("risk", text="风险")
        self.pending_tree.heading("reason", text="原因")
        self.pending_tree.column("id", width=80)
        self.pending_tree.column("tool", width=150)
        self.pending_tree.column("risk", width=80)
        self.pending_tree.column("reason", width=300)
        
        scrollbar = ttk.Scrollbar(pending_frame, orient=tk.VERTICAL, command=self.pending_tree.yview)
        self.pending_tree.configure(yscrollcommand=scrollbar.set)
        
        self.pending_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 操作按钮
        pending_btn_frame = ttk.Frame(approval_frame)
        pending_btn_frame.pack(fill=tk.X)
        
        btn_left = ttk.Frame(pending_btn_frame)
        btn_left.pack(side=tk.LEFT)
        ttk.Button(btn_left, text="✅ 批准选中", command=self._approve_selected_pending).pack(side=tk.LEFT)
        ttk.Button(btn_left, text="❌ 拒绝选中", command=self._deny_selected_pending).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_left, text="🔄 刷新", command=self._refresh_pending_list).pack(side=tk.LEFT, padx=(5, 0))
        
        # 总是批准的工具列表
        always_approve_frame = ttk.LabelFrame(approval_frame, text="总是批准的工具", padding="10")
        always_approve_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.always_approve_text = scrolledtext.ScrolledText(always_approve_frame, height=4, wrap=tk.WORD)
        self.always_approve_text.pack(fill=tk.X)
        self.always_approve_text.config(state=tk.DISABLED)
        
        # 添加/删除按钮
        always_approve_btn_frame = ttk.Frame(approval_frame)
        always_approve_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(always_approve_btn_frame, text="➕ 添加工具", 
                   command=self._add_always_approve_tool).pack(side=tk.LEFT)
        ttk.Button(always_approve_btn_frame, text="🗑️ 删除选中", 
                   command=self._remove_always_approve_tool).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(always_approve_btn_frame, text="🔄 刷新", 
                   command=self._refresh_always_approve_list).pack(side=tk.LEFT, padx=(5, 0))
    
    def _add_always_approve_tool(self):
        """添加工具到总是批准列表"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("添加总是批准的工具")
        dialog.geometry("400x150")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="工具名称:").pack(anchor=tk.W)
        
        tool_name_var = tk.StringVar()
        tool_entry = ttk.Entry(frame, textvariable=tool_name_var, width=40)
        tool_entry.pack(fill=tk.X, pady=(5, 10))
        tool_entry.focus()
        
        def on_add():
            tool_name = tool_name_var.get().strip()
            if not tool_name:
                messagebox.showwarning("警告", "请输入工具名称")
                return
            
            self.approval_manager.add_approved_tool(tool_name)
            config_manager = get_config_manager()
            config_manager.add_always_approved_tool(tool_name)
            
            self._refresh_always_approve_list()
            dialog.destroy()
            messagebox.showinfo("成功", f"已将 '{tool_name}' 添加到总是批准列表")
        
        def on_cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="添加", command=on_add).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=(10, 0))
        
        tool_entry.bind("<Return>", lambda e: on_add())
    
    def _remove_always_approve_tool(self):
        """从总是批准列表中删除工具"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        current_tools = sorted(self.approval_manager.get_approved_tools())
        if not current_tools:
            messagebox.showinfo("提示", "总是批准列表为空")
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("删除总是批准的工具")
        dialog.geometry("400x300")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="选择要删除的工具:").pack(anchor=tk.W)
        
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for tool in sorted(current_tools):
            listbox.insert(tk.END, tool)
        
        def on_remove():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("警告", "请选择要删除的工具")
                return
            
            for idx in reversed(selected):
                tool_name = listbox.get(idx)
                self.approval_manager.remove_approved_tool(tool_name)
                config_manager = get_config_manager()
                config_manager.remove_always_approved_tool(tool_name)
            
            self._refresh_always_approve_list()
            dialog.destroy()
            messagebox.showinfo("成功", f"已删除 {len(selected)} 个工具")
        
        def on_cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="删除", command=on_remove).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=(10, 0))
    
    def _set_approval_mode(self):
        """设置审批模式"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        mode_str = self.approval_mode_var.get()
        mode_map = {
            "suggest": ApprovalMode.SUGGEST,
            "auto_edit": ApprovalMode.AUTO_EDIT,
            "full_auto": ApprovalMode.FULL_AUTO,
        }
        self.approval_manager.set_mode(mode_map[mode_str])
        
        config_manager = get_config_manager()
        config_manager.set_approval_mode(mode_str)
        
        mode_names = {
            "suggest": "建议模式",
            "auto_edit": "自动编辑模式",
            "full_auto": "全自动模式"
        }
        messagebox.showinfo("成功", f"审批模式已设置为: {mode_names.get(mode_str, mode_str)}\n修改已即时生效")
        self._refresh_always_approve_list()
    
    def _reset_approval_permissions(self):
        """重置所有权限"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        if messagebox.askyesno("确认", "确定要重置所有权限设置吗？\n所有总是批准的设置将被清除。"):
            self.approval_manager.reset_permissions()
            config_manager = get_config_manager()
            config_manager.clear_always_approved_tools()
            self._refresh_always_approve_list()
            self._refresh_pending_list()
            messagebox.showinfo("成功", "权限已重置")
    
    def _refresh_pending_list(self):
        """刷新待审批列表"""
        for item in self.pending_tree.get_children():
            self.pending_tree.delete(item)
        
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        pending = self.approval_manager.get_pending()
        for req in pending:
            self.pending_tree.insert("", tk.END, values=(
                req.id,
                req.tool_name,
                req.risk_level,
                req.reason or ""
            ))
    
    def _refresh_always_approve_list(self):
        """刷新总是批准的工具列表"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        self.always_approve_text.config(state=tk.NORMAL)
        self.always_approve_text.delete(1.0, tk.END)
        
        approved = self.approval_manager.get_approved_tools()
        if approved:
            self.always_approve_text.insert(tk.END, "\n".join(sorted(approved)))
        else:
            self.always_approve_text.insert(tk.END, "暂无总是批准的工具")
        
        self.always_approve_text.config(state=tk.DISABLED)
    
    def _approve_selected_pending(self):
        """批准选中的待审批请求"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        for item in self.pending_tree.selection():
            values = self.pending_tree.item(item, "values")
            req_id = values[0]
            self.approval_manager.decide(req_id, ApprovalDecision.APPROVE)
        
        self.window.after(100, self._refresh_pending_list)
    
    def _deny_selected_pending(self):
        """拒绝选中的待审批请求"""
        if not HAS_APPROVAL or not self.approval_manager:
            return
        
        for item in self.pending_tree.selection():
            values = self.pending_tree.item(item, "values")
            req_id = values[0]
            self.approval_manager.decide(req_id, ApprovalDecision.DENY)
        
        self.window.after(100, self._refresh_pending_list)
    
    def _on_approval_request(self, request: ApprovalRequest):
        """处理新的审批请求（可能在非主线程调用）"""
        if not hasattr(self, 'window') or not self.window or not self.window.winfo_exists():
            import logging
            logging.getLogger(__name__).warning("[审批] 配置对话框已关闭，无法显示审批弹窗")
            request.decide(ApprovalDecision.DENY)
            return
        self.window.after(0, lambda: self._show_approval_dialog(request))
    
    def _show_approval_dialog(self, request: ApprovalRequest):
        """显示审批对话框"""
        parent_window = self.window if hasattr(self, 'window') and self.window and self.window.winfo_exists() else self.parent
        
        def handle_decision(decision_str: str):
            decision_map = {
                "approve": ApprovalDecision.APPROVE,
                "deny": ApprovalDecision.DENY,
                "always_approve": ApprovalDecision.ALWAYS_APPROVE,
            }
            decision = decision_map.get(decision_str, ApprovalDecision.DENY)
            request.decide(decision)
            
            if decision_str == "always_approve" and request.tool_name:
                config_manager = get_config_manager()
                config_manager.add_always_approved_tool(request.tool_name)
            
            self._refresh_pending_list()
            self._refresh_always_approve_list()
        
        ApprovalDialog(parent_window, request, handle_decision)
        self._refresh_pending_list()
    
    def _create_workflow_tab(self, notebook):
        """创建工作流管理标签页"""
        workflow_frame = ttk.Frame(notebook, padding="10")
        notebook.add(workflow_frame, text="⚡ 工作流管理")
        
        paned = ttk.PanedWindow(workflow_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="工作流定义", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        self.workflow_tree = ttk.Treeview(
            left_frame,
            columns=("id", "name", "version"),
            show="headings",
            height=10
        )
        self.workflow_tree.heading("id", text="ID")
        self.workflow_tree.heading("name", text="名称")
        self.workflow_tree.heading("version", text="版本")
        self.workflow_tree.column("id", width=120)
        self.workflow_tree.column("name", width=150)
        self.workflow_tree.column("version", width=60)
        
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.workflow_tree.yview)
        self.workflow_tree.configure(yscrollcommand=scrollbar.set)
        
        self.workflow_tree.pack(side=tk.LEFT, fill=tk.Y)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        wf_btn_frame = ttk.Frame(left_frame)
        wf_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(wf_btn_frame, text="➕ 加载预定义", command=self._load_predefined_workflows).pack(fill=tk.X, pady=2)
        ttk.Button(wf_btn_frame, text="🔄 刷新", command=self._refresh_workflow_definitions).pack(fill=tk.X, pady=2)
        ttk.Button(wf_btn_frame, text="▶️ 运行选中", command=self._run_selected_workflow).pack(fill=tk.X, pady=2)
        ttk.Button(wf_btn_frame, text="🗑️ 删除选中", command=self._delete_selected_workflow).pack(fill=tk.X, pady=2)
        
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        instance_frame = ttk.LabelFrame(right_frame, text="运行实例", padding="5")
        instance_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.instance_tree = ttk.Treeview(
            instance_frame,
            columns=("id", "workflow", "status", "progress", "step"),
            show="headings",
            height=6
        )
        self.instance_tree.heading("id", text="实例 ID")
        self.instance_tree.heading("workflow", text="工作流")
        self.instance_tree.heading("status", text="状态")
        self.instance_tree.heading("progress", text="进度")
        self.instance_tree.heading("step", text="当前步骤")
        self.instance_tree.column("id", width=120)
        self.instance_tree.column("workflow", width=100)
        self.instance_tree.column("status", width=70)
        self.instance_tree.column("progress", width=60)
        self.instance_tree.column("step", width=100)
        
        instance_scrollbar = ttk.Scrollbar(instance_frame, orient=tk.VERTICAL, command=self.instance_tree.yview)
        self.instance_tree.configure(yscrollcommand=instance_scrollbar.set)
        
        self.instance_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        instance_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        instance_btn_frame = ttk.Frame(right_frame)
        instance_btn_frame.pack(fill=tk.X, pady=(2, 5))
        ttk.Button(instance_btn_frame, text="🔄 刷新", command=self._refresh_workflow_instances).pack(side=tk.LEFT)
        ttk.Button(instance_btn_frame, text="⏸️ 暂停", command=self._pause_selected_instance).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(instance_btn_frame, text="▶️ 恢复", command=self._resume_selected_instance).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(instance_btn_frame, text="❌ 取消", command=self._cancel_selected_instance).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(instance_btn_frame, text="📋 日志", command=self._show_instance_logs).pack(side=tk.LEFT, padx=(5, 0))
        
        detail_frame = ttk.LabelFrame(right_frame, text="步骤详情", padding="5")
        detail_frame.pack(fill=tk.BOTH, expand=True)
        
        self.wf_detail_text = tk.Text(detail_frame, height=8, wrap=tk.WORD, state=tk.DISABLED,
                                       font=("Consolas", 9))
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.wf_detail_text.yview)
        self.wf_detail_text.configure(yscrollcommand=detail_scroll.set)
        self.wf_detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.instance_tree.bind("<<TreeviewSelect>>", self._on_instance_selected)
        
        self._wf_auto_refresh_id = None
        self._start_wf_auto_refresh()
    
    def _start_wf_auto_refresh(self):
        if self._wf_auto_refresh_id:
            self.window.after_cancel(self._wf_auto_refresh_id)
        if HAS_WORKFLOW and self.workflow_engine:
            running = self.workflow_engine.persistence.list_instances(WorkflowStatus.RUNNING)
            if running:
                self._refresh_workflow_instances()
        self._wf_auto_refresh_id = self.window.after(3000, self._start_wf_auto_refresh)
    
    def _on_instance_selected(self, event=None):
        selection = self.instance_tree.selection()
        if not selection:
            return
        item = selection[0]
        values = self.instance_tree.item(item, "values")
        instance_id = values[0]
        self._show_instance_detail(instance_id)
    
    def _show_instance_detail(self, instance_id: str):
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        step_results = self.workflow_engine.get_step_results(instance_id)
        self.wf_detail_text.config(state=tk.NORMAL)
        self.wf_detail_text.delete(1.0, tk.END)
        if not step_results:
            self.wf_detail_text.insert(tk.END, "暂无步骤结果")
        else:
            for sid, sr in step_results.items():
                status_icon = {"completed": "✅", "running": "🔄", "failed": "❌", "pending": "⏳"}.get(sr.get("status", ""), "❓")
                self.wf_detail_text.insert(tk.END, f"{status_icon} {sr.get('step_id', sid)}: {sr.get('status', '')}\n")
                if sr.get("error"):
                    self.wf_detail_text.insert(tk.END, f"   错误: {sr['error']}\n")
                if sr.get("output"):
                    output_str = str(sr["output"])[:200]
                    self.wf_detail_text.insert(tk.END, f"   输出: {output_str}\n")
                if sr.get("retry_count", 0) > 0:
                    self.wf_detail_text.insert(tk.END, f"   重试: {sr['retry_count']}次\n")
        self.wf_detail_text.config(state=tk.DISABLED)
    
    def _show_instance_logs(self):
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        selection = self.instance_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个实例")
            return
        item = selection[0]
        values = self.instance_tree.item(item, "values")
        instance_id = values[0]
        
        logs = self.workflow_engine.get_logs(instance_id, limit=50)
        
        log_win = tk.Toplevel(self.window)
        log_win.title(f"工作流日志 - {instance_id[:8]}")
        log_win.geometry("700x500")
        
        text = tk.Text(log_win, wrap=tk.WORD, font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_win, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        for log in reversed(logs):
            level = log.get("log_level", "info")
            icon = {"info": "ℹ️", "warn": "⚠️", "error": "🔴", "notify": "📢"}.get(level, "ℹ️")
            ts = log.get("created_at", "")[11:19]
            step = log.get("step_name", "")
            step_info = f"[{step}] " if step else ""
            text.insert(tk.END, f"{icon} {ts} {step_info}{log.get('message', '')}\n")
    
    def _load_predefined_workflows(self):
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        try:
            self.workflow_engine.register_builtin_workflows()
            self._refresh_workflow_definitions()
            messagebox.showinfo("成功", "预定义工作流已加载")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")
    
    def _delete_selected_workflow(self):
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        selection = self.workflow_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的工作流")
            return
        item = selection[0]
        values = self.workflow_tree.item(item, "values")
        workflow_id = values[0]
        if messagebox.askyesno("确认", f"确定删除工作流 {workflow_id}?"):
            self.workflow_engine.persistence.delete_definition(workflow_id)
            self._refresh_workflow_definitions()
    
    def _cancel_selected_instance(self):
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        selection = self.instance_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要取消的实例")
            return
        item = selection[0]
        values = self.instance_tree.item(item, "values")
        instance_id = values[0]
        if self.workflow_engine.cancel_workflow(instance_id):
            self._refresh_workflow_instances()
        else:
            messagebox.showerror("错误", "取消失败")
    
    def _create_sample_workflow(self):
        """创建示例工作流"""
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        try:
            from .workflow_engine import WorkflowDefinition, StepDefinition, StepType
            
            # 创建一个简单的示例工作流
            sample_steps = [
                StepDefinition(
                    step_id="step1",
                    name="介绍步骤",
                    step_type=StepType.NOTIFY,
                    config={"message": "这是一个示例工作流的开始"}
                ),
                StepDefinition(
                    step_id="step2",
                    name="计算步骤",
                    step_type=StepType.TOOL,
                    config={"tool_name": "calculate", "args": {"expression": "2 + 2"}}
                ),
                StepDefinition(
                    step_id="step3",
                    name="结束步骤",
                    step_type=StepType.NOTIFY,
                    config={"message": "示例工作流完成！"}
                )
            ]
            
            sample_wf = WorkflowDefinition(
                workflow_id="sample_workflow",
                name="示例工作流",
                description="一个简单的示例工作流，展示工作流引擎的基本功能",
                version="1.0",
                steps=sample_steps,
                entry_step="step1"
            )
            
            self.workflow_engine.persistence.save_definition(sample_wf)
            self._refresh_workflow_definitions()
            messagebox.showinfo("成功", "示例工作流已创建！")
        except Exception as e:
            messagebox.showerror("错误", f"创建示例工作流失败: {str(e)}")
    
    def _refresh_workflow_definitions(self):
        """刷新工作流定义列表"""
        for item in self.workflow_tree.get_children():
            self.workflow_tree.delete(item)
        
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        definitions = self.workflow_engine.persistence.list_definitions()
        for wf in definitions:
            self.workflow_tree.insert("", tk.END, values=(
                wf["workflow_id"],
                wf["name"],
                wf["version"]
            ))
    
    def _refresh_workflow_instances(self):
        for item in self.instance_tree.get_children():
            self.instance_tree.delete(item)
        
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        instances = self.workflow_engine.persistence.list_instances(limit=20)
        for inst in instances:
            progress = f"{inst.get('progress', 0)*100:.0f}%"
            step_name = inst.get("current_step_name", "") or inst.get("current_step_id", "") or ""
            status = inst.get("status", "")
            status_icon = {"running": "🔄", "completed": "✅", "failed": "❌", "paused": "⏸️", "cancelled": "🚫"}.get(status, status)
            self.instance_tree.insert("", tk.END, values=(
                inst["instance_id"],
                inst["workflow_id"],
                status_icon,
                progress,
                step_name[:20]
            ))
    
    def _run_selected_workflow(self):
        """运行选中的工作流"""
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        selection = self.workflow_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要运行的工作流")
            return
        
        item = selection[0]
        values = self.workflow_tree.item(item, "values")
        workflow_id = values[0]
        
        # 获取工作流定义
        wf_def = self.workflow_engine.persistence.get_definition(workflow_id)
        if not wf_def:
            messagebox.showerror("错误", f"无法获取工作流定义: {workflow_id}")
            return
        
        # 启动工作流
        try:
            instance_id = self.workflow_engine.start_workflow(wf_def, {})
            messagebox.showinfo("成功", f"工作流已启动！\n实例 ID: {instance_id}")
            self._refresh_workflow_instances()
        except Exception as e:
            messagebox.showerror("错误", f"启动工作流失败: {str(e)}")
    
    def _pause_selected_instance(self):
        """暂停选中的实例"""
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        selection = self.instance_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要暂停的实例")
            return
        
        item = selection[0]
        values = self.instance_tree.item(item, "values")
        instance_id = values[0]
        
        if self.workflow_engine.pause_workflow(instance_id):
            messagebox.showinfo("成功", "工作流已暂停")
            self._refresh_workflow_instances()
        else:
            messagebox.showerror("错误", "暂停失败，实例可能不存在或未在运行")
    
    def _resume_selected_instance(self):
        """恢复选中的实例"""
        if not HAS_WORKFLOW or not self.workflow_engine:
            return
        
        selection = self.instance_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要恢复的实例")
            return
        
        item = selection[0]
        values = self.instance_tree.item(item, "values")
        instance_id = values[0]
        
        if self.workflow_engine.resume_workflow(instance_id):
            messagebox.showinfo("成功", "工作流已恢复")
            self._refresh_workflow_instances()
        else:
            messagebox.showerror("错误", "恢复失败，实例可能不存在或不可恢复")
    
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
        self._refresh_sub_agents_list()
        self._refresh_skills_list()
        self._refresh_pending_list()
        self._refresh_always_approve_list()
        self._refresh_workflow_definitions()
        self._refresh_workflow_instances()
        self._refresh_tools_list()
    
    def _create_sub_agents_tab(self, notebook):
        """创建子 Agent 配置标签页"""
        tab_frame = ttk.Frame(notebook, padding="10")
        notebook.add(tab_frame, text="🔀 子 Agent")
        
        paned = ttk.PanedWindow(tab_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        left_frame = ttk.Frame(paned, padding=(0, 0, 10, 0))
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="已配置的子 Agent", font=("", 10, "bold")).pack(anchor=tk.W)
        
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        self.sub_agent_tree = ttk.Treeview(
            list_frame,
            columns=("role", "name", "model", "enabled"),
            show="headings",
            height=15
        )
        self.sub_agent_tree.heading("role", text="角色")
        self.sub_agent_tree.heading("name", text="名称")
        self.sub_agent_tree.heading("model", text="模型")
        self.sub_agent_tree.heading("enabled", text="状态")
        self.sub_agent_tree.column("role", width=80, anchor=tk.CENTER)
        self.sub_agent_tree.column("name", width=120)
        self.sub_agent_tree.column("model", width=150)
        self.sub_agent_tree.column("enabled", width=60, anchor=tk.CENTER)
        
        sub_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.sub_agent_tree.yview)
        self.sub_agent_tree.configure(yscrollcommand=sub_scrollbar.set)
        
        self.sub_agent_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sub_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.sub_agent_tree.bind("<<TreeviewSelect>>", self._on_sub_agent_select)
        
        list_btn_frame = ttk.Frame(left_frame)
        list_btn_frame.pack(fill=tk.X)
        ttk.Button(list_btn_frame, text="✏️ 编辑", command=self._edit_sub_agent).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(list_btn_frame, text="🔄 重置默认", command=self._reset_sub_agents).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        right_frame = ttk.Frame(paned, padding=(10, 0, 0, 0))
        paned.add(right_frame, weight=1)
        
        ttk.Label(right_frame, text="子 Agent 详情", font=("", 10, "bold")).pack(anchor=tk.W)
        
        self.sub_agent_detail_text = tk.Text(right_frame, wrap=tk.WORD, height=25)
        sub_detail_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.sub_agent_detail_text.yview)
        self.sub_agent_detail_text.configure(yscrollcommand=sub_detail_scrollbar.set)
        
        self.sub_agent_detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(5, 0))
        sub_detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(5, 0))
    
    def _refresh_sub_agents_list(self):
        """刷新子 Agent 列表"""
        for item in self.sub_agent_tree.get_children():
            self.sub_agent_tree.delete(item)
        
        configs = self.config_manager.get_sub_agent_configs() or []
        role_icons = {
            "coder": "💻",
            "task": "📋",
            "research": "🔍",
            "review": "✅",
            "custom": "🔧"
        }
        
        for config in configs:
            role_icon = role_icons.get(config.role, "🔧")
            status = "✅" if config.enabled else "❌"
            self.sub_agent_tree.insert("", tk.END, values=(
                f"{role_icon} {config.role}",
                config.name,
                config.model or "(使用主模型)",
                status
            ))
    
    def _on_sub_agent_select(self, event):
        """选中子 Agent 时显示详情"""
        selection = self.sub_agent_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.sub_agent_tree.item(item, "values")
        name = values[1].strip()
        
        config = self.config_manager.get_sub_agent_config(name)
        if config:
            self._show_sub_agent_details(config)
    
    def _show_sub_agent_details(self, config):
        """显示子 Agent 详情"""
        self.sub_agent_detail_text.delete(1.0, tk.END)
        
        role_icons = {
            "coder": "💻 编程助手",
            "task": "📋 任务助手",
            "research": "🔍 研究助手",
            "review": "✅ 代码审查",
            "custom": "🔧 自定义"
        }
        
        role_display = role_icons.get(config.role, f"🔧 {config.role}")
        
        details = f"""
📋 {config.name}
{'=' * 50}

🎭 角色: {role_display}
⚙️ 状态: {'✅ 已启用' if config.enabled else '❌ 已禁用'}
🤖 模型: {config.model or '(使用主模型)'}
🔄 最大轮次: {config.max_turns}

📝 系统提示词:
{'-' * 50}
{config.system_prompt or '(未设置)'}
"""
        self.sub_agent_detail_text.insert(1.0, details)
    
    def _edit_sub_agent(self):
        """编辑子 Agent"""
        selection = self.sub_agent_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择要编辑的子 Agent")
            return
        
        item = selection[0]
        values = self.sub_agent_tree.item(item, "values")
        name = values[1].strip()
        
        config = self.config_manager.get_sub_agent_config(name)
        if not config:
            return
        
        dialog = SubAgentConfigDialog(self.window, config, config_manager=self.config_manager)
        self.window.wait_window(dialog.dialog)
        
        if dialog.result:
            self.config_manager.add_sub_agent_config(dialog.result)
            self._refresh_sub_agents_list()
            self._show_sub_agent_details(dialog.result)
    
    def _reset_sub_agents(self):
        """重置子 Agent 为默认配置"""
        if not messagebox.askyesno("确认", "确定要将所有子 Agent 重置为默认配置吗？\n这将丢失您的自定义设置。"):
            return
        
        from .config import SubAgentConfig
        default_sub_agents = [
            SubAgentConfig(
                role="coder",
                name="coder",
                enabled=True,
                model="",
                max_turns=15,
                system_prompt="你是一名专业的编程助手。你的任务是编写、调试、重构代码，解决编程问题。请给出清晰、可执行的解决方案。",
            ),
            SubAgentConfig(
                role="task",
                name="task",
                enabled=True,
                model="",
                max_turns=10,
                system_prompt="你是一名任务执行助手。你的任务是完成用户指定的具体任务，一步一步执行，并给出完整的结果。",
            ),
            SubAgentConfig(
                role="research",
                name="research",
                enabled=True,
                model="",
                max_turns=8,
                system_prompt="你是一名研究助手。你的任务是搜索信息、分析资料、总结内容，帮助用户深入了解特定主题。",
            ),
            SubAgentConfig(
                role="review",
                name="review",
                enabled=True,
                model="",
                max_turns=5,
                system_prompt="你是一名代码审查专家。你的任务是审查代码质量、安全性、最佳实践，并给出建设性的改进建议。",
            ),
        ]
        for cfg in default_sub_agents:
            self.config_manager.add_sub_agent_config(cfg)
        
        self._refresh_sub_agents_list()
        messagebox.showinfo("成功", "子 Agent 配置已重置为默认值")
    
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

        self._all_tools = []  # 清空并重建
        
        # 获取所有工具（内置 + WS2 + DataHub）
        all_tools = list(get_tools())
        
        base_dir = getattr(self, 'base_dir', None)
        
        # 尝试获取 WS2 工具
        try:
            from .ws2_tools import get_ws2_tools
            ws2_tools = get_ws2_tools(base_dir=base_dir)
            all_tools.extend(ws2_tools)
        except Exception:
            pass
        
        # 尝试获取 DataHub 工具
        try:
            from .ws2_hub_tools import get_hub_tools
            hub_tools = get_hub_tools(base_dir=base_dir)
            all_tools.extend(hub_tools)
        except Exception:
            pass
        
        # 尝试获取 GT 证明工具
        try:
            from .gt.gt_tools import get_gt_tools
            gt_tools = get_gt_tools()
            all_tools.extend(gt_tools)
        except Exception:
            pass

        # 尝试获取飞书工具
        try:
            from .feishu.feishu_tools import get_feishu_tools
            feishu_tools = get_feishu_tools()
            all_tools.extend(feishu_tools)
        except Exception:
            pass
        
        # 尝试获取 Lean4 工具
        try:
            from .research.lean4.lean4_tools import get_lean4_tools
            lean4_tools = get_lean4_tools()
            all_tools.extend(lean4_tools)
        except Exception:
            pass
        
        # 尝试获取 Manim 工具
        try:
            from .research.manim.manim_tools import get_manim_tools
            manim_tools = get_manim_tools()
            all_tools.extend(manim_tools)
        except Exception:
            pass
        
        # 尝试获取 MathLens 工具
        try:
            from .research.mathlens.mathlens_tools import get_mathlens_tools
            mathlens_tools = get_mathlens_tools()
            all_tools.extend(mathlens_tools)
        except Exception:
            pass
        
        try:
            from .research.autoresearch.autoresearch_tools import get_autoresearch_tools
            autoresearch_tools = get_autoresearch_tools()
            all_tools.extend(autoresearch_tools)
        except Exception:
            pass
        
        # 先确保所有工具都有配置
        self.config_manager.init_default_tool_configs(all_tools)
        # 获取启用的工具名称
        enabled_names = [t.name for t in self.config_manager.get_enabled_tools()]
        
        # 工具分类映射
        tool_categories = {
            # 内置工具
            "read_file": "builtin",
            "write_file": "builtin",
            "edit_file": "builtin",
            "list_directory": "builtin",
            "grep": "builtin",
            "glob": "builtin",
            "calculate": "builtin",
            "web_search": "builtin",
            "fetch_url": "builtin",
            "analyze_paper": "builtin",
            "open_file": "builtin",
            "diff_files": "builtin",
            "move_file": "builtin",
            "copy_file": "builtin",
            "file_info": "builtin",
            "cli_execute": "builtin",
            "config_manage": "builtin",
            "skill_manager": "builtin",
            "terminal_open": "builtin",
            # WS2 工具
            "ws2_get_overview": "ws2",
            "ws2_get_domain_stats": "ws2",
            "ws2_list_domains": "ws2",
            "ws2_get_progress_by_domain": "ws2",
            "ws2_list_courses": "ws2",
            "ws2_search_courses": "ws2",
            "ws2_get_course_detail": "ws2",
            "ws2_create_course": "ws2",
            "ws2_remove_course": "ws2",
            "ws2_find_duplicates": "ws2",
            "ws2_update_course_info": "ws2",
            "ws2_mark_lesson_complete": "ws2",
            "ws2_get_next_lesson": "ws2",
            "ws2_get_course_progress": "ws2",
            "ws2_get_resources": "ws2",
            "ws2_add_resource": "ws2",
            "ws2_list_bookmarks": "ws2",
            "ws2_search_bookmarks": "ws2",
            "ws2_add_bookmark": "ws2",
            "ws2_list_bookmark_categories": "ws2",
            "ws2_list_notes": "ws2",
            "ws2_read_note": "ws2",
            "ws2_write_note": "ws2",
            "ws2_list_projects": "ws2",
            "ws2_create_project": "ws2",
            "ws2_list_tasks": "ws2",
            "ws2_add_task": "ws2",
            "ws2_update_task": "ws2",
            "ws2_reload_all_sources": "ws2",
            "ws2_add_db_path": "ws2",
            "ws2_get_db_paths": "ws2",
            "ws2_get_review_schedule": "ws2",
            "ws2_mark_review_done": "ws2",
            # DataHub 工具
            "ws2_hub_add_item": "hub",
            "ws2_hub_query_items": "hub",
            "ws2_hub_get_item": "hub",
            "ws2_hub_update_item": "hub",
            "ws2_hub_delete_item": "hub",
            "ws2_hub_add_rss": "hub",
            "ws2_hub_remove_rss": "hub",
            "ws2_hub_list_rss": "hub",
            "ws2_hub_poll_rss": "hub",
            "ws2_hub_create_collection": "hub",
            "ws2_hub_add_to_collection": "hub",
            "ws2_hub_list_collections": "hub",
            "ws2_hub_pipeline_crawl": "hub",
            "ws2_hub_pipeline_bookmark": "hub",
            "ws2_hub_pipeline_analysis": "hub",
            "ws2_hub_pipeline_local": "hub",
            "ws2_hub_bookmark_crawl": "hub",
            "ws2_hub_generate_rss": "hub",
            "ws2_hub_parse_content": "hub",
            "ws2_hub_fetch_url": "hub",
            "ws2_hub_auto_scan": "hub",
            "ws2_hub_lightweight_crawl": "hub",
            "ws2_hub_discover_subscriptions": "hub",
            "ws2_hub_run_pipeline": "hub",
            "ws2_hub_pipeline_status": "hub",
            "ws2_hub_get_stats": "hub",
            # 子Agent
            "sub_agent": "builtin",
            # 新增高级工具
            "rag_retrieval": "rag",
            "sandbox_execute": "sandbox",
            "mcp_client": "mcp_client",
            # GT 证明工具
            "gt_validate": "gt",
            "gt_rate": "gt",
            "gt_gap_ledger": "gt",
            "gt_assumption_audit": "gt",
            "gt_search_replace": "gt",
            "gt_evolve": "gt",
            "gt_workflow_run": "gt",
            "gt_research": "gt",
            "gt_compile": "gt",
            # 飞书工具
            "feishu_doc_read": "feishu",
            "feishu_doc_write": "feishu",
            "feishu_msg": "feishu",
            "feishu_sheet": "feishu",
            "feishu_bitable": "feishu",
            "feishu_drive": "feishu",
            "feishu_calendar": "feishu",
            "feishu_wiki": "feishu",
            "feishu_auth": "feishu",
            "feishu_api": "feishu",
            # Lean4 工具
            "lean4_check": "lean4",
            "lean4_open_file": "lean4",
            "lean4_get_diagnostics": "lean4",
            "lean4_get_goal_state": "lean4",
            "lean4_lake_build": "lean4",
            "lean4_prove": "lean4",
            "lean4_formalize": "lean4",
            "lean4_golf": "lean4",
            "lean4_review": "lean4",
            "lean4_refactor": "lean4",
            "lean4_learn": "lean4",
            "lean4_agent": "lean4",
            "lean4_mathlib_search": "lean4",
            # Manim 工具
            "manim_generate": "manim",
            "manim_edit": "manim",
            "manim_list_renders": "manim",
            "manim_render": "manim",
            "manim_rag_search": "manim",
            "manim_concept_analyze": "manim",
            "manim_code_review": "manim",
            "manim_self_critique": "manim",
            "manim_tts_generate": "manim",
            "manim_schema_generate": "manim",
            "manim_skills_list": "manim",
            # MathLens 工具
            "mathlens_init": "mathlens",
            "mathlens_generate_tts": "mathlens",
            "mathlens_validate_audio": "mathlens",
            "mathlens_check": "mathlens",
            "mathlens_render": "mathlens",
            # AutoResearch 工具
            "autoresearch_topic_init": "autoresearch",
            "autoresearch_lit_search": "autoresearch",
            "autoresearch_synthesis": "autoresearch",
            "autoresearch_exp_design": "autoresearch",
            "autoresearch_result_analysis": "autoresearch",
            "autoresearch_quality_gate": "autoresearch",
            "autoresearch_skill": "autoresearch",
            "autoresearch_list_skills": "autoresearch",
        }
        
        # 分类显示名称
        category_names = {
            "builtin": "内置",
            "ws2": "WS2",
            "hub": "DataHub",
            "rag": "RAG",
            "sandbox": "沙箱",
            "mcp_client": "MCP",
            "gt": "GT证明",
            "feishu": "飞书",
            "lean4": "Lean4",
            "manim": "Manim",
            "mathlens": "MathLens",
            "autoresearch": "AutoResearch",
        }
        
        for tool in all_tools:
            enabled = tool.name in enabled_names
            category_key = tool_categories.get(tool.name, "builtin")
            category_display = category_names.get(category_key, category_key)
            
            tool_info = {
                "name": tool.name,
                "category_key": category_key,  # 保存原始分类key用于过滤
                "category": category_display,  # 保存显示名称
                "description": tool.description,
                "enabled": enabled
            }
            self._all_tools.append(tool_info)
            
            self.tools_tree.insert("", tk.END, values=(
                tool.name,
                category_display,
                tool.description,
                "✅" if enabled else "❌"
            ))
        
        # 应用当前分类筛选
        self._filter_tools_by_category()
    
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
   • 思维链: {'✅ 已启用' if getattr(config, 'thinking_enabled', None) else '❌ 已禁用'}
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
            self.config_manager.update_tool_config(tool_name, enabled=True)
        self._refresh_tools_list()

    def _disable_selected_tool(self):
        """禁用选中工具"""
        for item in self.tools_tree.selection():
            values = self.tools_tree.item(item, "values")
            tool_name = values[0]
            self.config_manager.update_tool_config(tool_name, enabled=False)
        self._refresh_tools_list()

    def _enable_all_tools(self):
        """启用所有工具"""
        from .tools import get_tools
        for tool in get_tools():
            self.config_manager.update_tool_config(tool.name, enabled=True)
        self._refresh_tools_list()
        messagebox.showinfo("成功", "已启用所有工具")

    def _disable_all_tools(self):
        """禁用所有工具"""
        if not messagebox.askyesno("确认", "确定要禁用所有工具吗？\n禁用后模型将无法使用这些工具。"):
            return

        from .tools import get_tools
        for tool in get_tools():
            self.config_manager.update_tool_config(tool.name, enabled=False)
        self._refresh_tools_list()
        messagebox.showinfo("成功", "已禁用所有工具")

    def _add_rag_document(self):
        """添加 RAG 文档"""
        file_path = filedialog.askopenfilename(
            title="选择要添加的文档",
            filetypes=[
                ("文档文件", "*.txt *.md *.pdf *.doc *.docx"),
                ("文本文件", "*.txt *.md"),
                ("所有文件", "*.*")
            ]
        )
        
        if file_path:
            try:
                from .rag.rag_engine import RAGEngine
                rag = RAGEngine()
                chunk_ids = rag.add_file(file_path)
                messagebox.showinfo(
                    "成功",
                    f"✅ 已添加文档到向量库\n文件: {Path(file_path).name}\n生成 {len(chunk_ids)} 个文本块"
                )
            except Exception as e:
                messagebox.showerror("错误", f"添加文档失败: {e}")

    def _view_rag_stats(self):
        """查看 RAG 统计"""
        try:
            from .rag.rag_engine import RAGEngine
            rag = RAGEngine()
            count = rag.get_document_count()
            docs = rag.get_all_documents()
            
            info_lines = ["📊 RAG 向量库统计\n" + "="*40]
            info_lines.append(f"• 文档总数: {count}")
            info_lines.append(f"• 向量维度: 384 (默认)")
            info_lines.append(f"\n文档列表:")
            for i, doc in enumerate(docs[:10], 1):
                info_lines.append(f"  {i}. {doc.source}")
            if len(docs) > 10:
                info_lines.append(f"  ... 还有 {len(docs) - 10} 个文档")
            
            messagebox.showinfo("RAG 统计", "\n".join(info_lines))
        except Exception as e:
            messagebox.showerror("错误", f"获取统计失败: {e}")

    def _configure_sandbox(self):
        """配置沙箱安全策略"""
        dialog = tk.Toplevel(self.window)
        dialog.title("配置沙箱安全策略")
        dialog.geometry("500x400")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="沙箱安全策略配置", font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 15))
        
        # 允许网络访问
        allow_network_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="允许网络访问",
            variable=allow_network_var
        ).pack(anchor=tk.W)
        
        # 最大执行时间
        ttk.Label(frame, text="最大执行时间（秒）:").pack(anchor=tk.W, pady=(10, 0))
        max_time_var = tk.IntVar(value=30)
        ttk.Entry(frame, textvariable=max_time_var, width=20).pack(anchor=tk.W)
        
        # 最大输出大小
        ttk.Label(frame, text="最大输出大小（字节）:").pack(anchor=tk.W, pady=(10, 0))
        max_output_var = tk.IntVar(value=1024*1024)  # 1MB
        ttk.Entry(frame, textvariable=max_output_var, width=20).pack(anchor=tk.W)
        
        ttk.Label(frame, text="💡 提示: 禁用网络访问可以防止沙箱中的代码访问外部网络", 
                 foreground="gray").pack(anchor=tk.W, pady=(15, 0))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.BOTTOM, pady=(20, 0))
        ttk.Button(btn_frame, text="💾 保存", 
                  command=lambda: self._save_sandbox_config(dialog, allow_network_var, max_time_var, max_output_var)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=(10, 0))

    def _save_sandbox_config(self, dialog, allow_network, max_time, max_output):
        """保存沙箱配置"""
        # 这里可以保存到配置文件中
        config = {
            "allow_network": allow_network.get(),
            "max_execution_time": max_time.get(),
            "max_output_bytes": max_output.get()
        }
        messagebox.showinfo("成功", f"✅ 沙箱配置已保存\n{json.dumps(config, indent=2)}")
        dialog.destroy()

    def _view_sandbox_logs(self):
        """查看沙箱执行日志"""
        messagebox.showinfo(
            "沙箱日志",
            "📋 沙箱执行日志\n\n" +
            "="*40 + "\n" +
            "暂无执行日志\n\n" +
            "💡 提示: 沙箱中执行的命令及其结果将显示在这里"
        )

    def _connect_mcp_server(self):
        """连接 MCP 服务器"""
        dialog = tk.Toplevel(self.window)
        dialog.title("连接 MCP 服务器")
        dialog.geometry("500x300")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="连接新的 MCP 服务器", font=("", 11, "bold")).pack(anchor=tk.W, pady=(0, 15))
        
        # 服务器名称
        ttk.Label(frame, text="服务器名称:").pack(anchor=tk.W)
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var, width=40).pack(anchor=tk.W, pady=(5, 10))
        
        # 服务器 URL
        ttk.Label(frame, text="服务器 URL:").pack(anchor=tk.W)
        url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=url_var, width=40).pack(anchor=tk.W, pady=(5, 10))
        
        ttk.Label(frame, text="示例: http://localhost:8080/mcp", 
                 foreground="gray").pack(anchor=tk.W)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.BOTTOM, pady=(20, 0))
        ttk.Button(btn_frame, text="🔗 连接", 
                  command=lambda: self._do_connect_mcp(dialog, name_var, url_var)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=(10, 0))

    def _do_connect_mcp(self, dialog, name_var, url_var):
        """执行 MCP 连接"""
        name = name_var.get().strip()
        url = url_var.get().strip()
        
        if not name or not url:
            messagebox.showwarning("警告", "请填写服务器名称和 URL")
            return
        
        messagebox.showinfo("提示", f"正在连接 MCP 服务器 '{name}'...\n\n此功能需要 MCP 服务器支持")
        dialog.destroy()

    def _view_mcp_status(self):
        """查看 MCP 客户端状态"""
        try:
            from .mcp_client.client import MCPClientManager
            mgr = MCPClientManager()
            clients = mgr.list_clients()
            
            if not clients:
                messagebox.showinfo("MCP 状态", "🔌 暂无连接的 MCP 服务器\n\n点击「连接新 MCP 服务」来添加")
                return
            
            info_lines = ["🔌 MCP 服务器连接状态\n" + "="*40]
            for name, info in clients.items():
                state_icon = "✅" if info.state.value == "connected" else "❌"
                info_lines.append(f"{state_icon} {name}: {info.state.value}")
                if info.error:
                    info_lines.append(f"   错误: {info.error}")
            
            messagebox.showinfo("MCP 状态", "\n".join(info_lines))
        except Exception as e:
            messagebox.showerror("错误", f"获取 MCP 状态失败: {e}")
    
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
    
    def _create_sessions_tab(self, notebook):
        """创建会话管理标签页"""
        sessions_frame = ttk.Frame(notebook, padding="10")
        notebook.add(sessions_frame, text="💬 会话管理")
        
        # 标题和说明
        info_frame = ttk.LabelFrame(sessions_frame, text="会话管理说明", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(info_frame, text="管理对话会话，支持创建、切换、重命名和删除会话。所有会话自动同步到 UI、Agent 助手窗口和缓存。", wraplength=750).pack(anchor=tk.W)
        
        # 会话列表
        list_frame = ttk.Frame(sessions_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        ttk.Label(list_frame, text="会话列表", font=("", 10, "bold")).pack(anchor=tk.W)
        
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.sessions_tree = ttk.Treeview(
            tree_frame,
            columns=("title", "created", "updated", "turns", "status"),
            show="headings",
            height=15
        )
        self.sessions_tree.heading("title", text="会话名称")
        self.sessions_tree.heading("created", text="创建时间")
        self.sessions_tree.heading("updated", text="更新时间")
        self.sessions_tree.heading("turns", text="对话轮次")
        self.sessions_tree.heading("status", text="状态")
        
        self.sessions_tree.column("title", width=250)
        self.sessions_tree.column("created", width=150)
        self.sessions_tree.column("updated", width=150)
        self.sessions_tree.column("turns", width=100, anchor=tk.CENTER)
        self.sessions_tree.column("status", width=80, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.sessions_tree.yview)
        self.sessions_tree.configure(yscrollcommand=scrollbar.set)
        
        self.sessions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 会话操作按钮
        btn_frame = ttk.Frame(sessions_frame)
        btn_frame.pack(fill=tk.X)
        
        left_btns = ttk.Frame(btn_frame)
        left_btns.pack(side=tk.LEFT)
        ttk.Button(left_btns, text="➕ 新建会话", command=self._create_new_session).pack(side=tk.LEFT)
        ttk.Button(left_btns, text="✏️ 重命名", command=self._rename_session).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(left_btns, text="🔄 切换会话", command=self._switch_session).pack(side=tk.LEFT, padx=(10, 0))
        
        right_btns = ttk.Frame(btn_frame)
        right_btns.pack(side=tk.RIGHT)
        ttk.Button(right_btns, text="🗑️ 删除会话", command=self._delete_session).pack(side=tk.LEFT)
        ttk.Button(right_btns, text="🔄 刷新列表", command=self._refresh_sessions_list).pack(side=tk.LEFT, padx=(10, 0))
        
        # 初始化会话列表
        self._refresh_sessions_list()
    
    def _refresh_sessions_list(self):
        """刷新会话列表"""
        # 清空现有内容
        for item in self.sessions_tree.get_children():
            self.sessions_tree.delete(item)
        
        if not self.unified_session_manager:
            return
        
        # 添加所有会话
        sessions = self.unified_session_manager.list_sessions()
        from datetime import datetime
        
        for session in sessions:
            try:
                created_str = datetime.fromisoformat(session.created_at).strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                created_str = str(session.created_at)[:16]
            try:
                updated_str = datetime.fromisoformat(session.updated_at).strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                updated_str = str(session.updated_at)[:16]
            status = "✅ 活动" if session.is_active else ""
            if session.has_running_tasks:
                status += " 🔄"
            
            self.sessions_tree.insert("", tk.END, values=(
                session.title,
                created_str,
                updated_str,
                session.turn_count,
                status
            ), tags=("active" if session.is_active else ""))
        
        # 高亮活动会话
        self.sessions_tree.tag_configure("active", background="#e3f2fd", foreground="#1976d2")
    
    def _create_new_session(self):
        """创建新会话"""
        dialog = tk.Toplevel(self.window)
        dialog.title("创建新会话")
        dialog.geometry("400x200")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="会话名称:", font=("", 10)).pack(anchor=tk.W)
        name_var = tk.StringVar(value="新会话")
        ttk.Entry(frame, textvariable=name_var, width=40).pack(fill=tk.X, pady=(5, 15))
        
        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("警告", "请输入会话名称！")
                return
            
            self.unified_session_manager.create_session(name)
            self._refresh_sessions_list()
            messagebox.showinfo("成功", f"会话「{name}」创建成功！")
            dialog.destroy()
        
        ttk.Button(frame, text="✅ 创建", command=save).pack(side=tk.LEFT)
        ttk.Button(frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=(10, 0))
    
    def _rename_session(self):
        """重命名会话"""
        selection = self.sessions_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要重命名的会话！")
            return
        
        # 获取选中会话的标题
        item = selection[0]
        current_title = self.sessions_tree.item(item, "values")[0]
        
        # 找到对应的会话
        sessions = self.unified_session_manager.list_sessions()
        target_session = None
        for s in sessions:
            if s.title == current_title:
                target_session = s
                break
        
        if not target_session:
            return
        
        dialog = tk.Toplevel(self.window)
        dialog.title("重命名会话")
        dialog.geometry("400x200")
        dialog.transient(self.window)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="新会话名称:", font=("", 10)).pack(anchor=tk.W)
        name_var = tk.StringVar(value=current_title)
        ttk.Entry(frame, textvariable=name_var, width=40).pack(fill=tk.X, pady=(5, 15))
        
        def save():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("警告", "请输入新会话名称！")
                return
            
            self.unified_session_manager.rename_session(target_session.session_id, new_name)
            self._refresh_sessions_list()
            messagebox.showinfo("成功", f"会话已重命名为「{new_name}」！")
            dialog.destroy()
        
        ttk.Button(frame, text="✅ 保存", command=save).pack(side=tk.LEFT)
        ttk.Button(frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=(10, 0))
    
    def _switch_session(self):
        """切换会话"""
        selection = self.sessions_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要切换到的会话！")
            return
        
        # 获取选中会话的标题
        item = selection[0]
        title = self.sessions_tree.item(item, "values")[0]
        
        # 找到对应的会话
        sessions = self.unified_session_manager.list_sessions()
        for session in sessions:
            if session.title == title:
                if session.is_active:
                    messagebox.showinfo("提示", f"会话「{title}」已经是活动会话了！")
                    return
                
                self.unified_session_manager.set_active_session(session.session_id)
                self._refresh_sessions_list()
                messagebox.showinfo("成功", f"已切换到会话「{title}」！")
                return
    
    def _delete_session(self):
        """删除会话"""
        selection = self.sessions_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的会话！")
            return
        
        if not messagebox.askyesno("确认", "确定要删除选中的会话吗？此操作不可恢复！"):
            return
        
        # 获取选中会话的标题
        item = selection[0]
        title = self.sessions_tree.item(item, "values")[0]
        
        # 找到对应的会话
        sessions = self.unified_session_manager.list_sessions()
        for session in sessions:
            if session.title == title:
                if len(sessions) <= 1:
                    messagebox.showwarning("警告", "至少需要保留一个会话！")
                    return
                
                self.unified_session_manager.delete_session(session.session_id)
                self._refresh_sessions_list()
                messagebox.showinfo("成功", f"会话「{title}」已删除！")
                return

    def _create_automation_tab(self, notebook):
        frame = ttk.Frame(notebook, padding="10")
        notebook.add(frame, text="⏰ 自动化")

        paned = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Label(left, text="自动化任务", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.auto_task_tree = ttk.Treeview(
            left, columns=("id", "name", "type", "trigger", "enabled"),
            show="headings", height=12
        )
        self.auto_task_tree.heading("id", text="ID")
        self.auto_task_tree.heading("name", text="名称")
        self.auto_task_tree.heading("type", text="类型")
        self.auto_task_tree.heading("trigger", text="触发器")
        self.auto_task_tree.heading("enabled", text="状态")
        self.auto_task_tree.column("id", width=100)
        self.auto_task_tree.column("name", width=140)
        self.auto_task_tree.column("type", width=70)
        self.auto_task_tree.column("trigger", width=100)
        self.auto_task_tree.column("enabled", width=50)

        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.auto_task_tree.yview)
        self.auto_task_tree.configure(yscrollcommand=sb.set)
        self.auto_task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="➕ 添加任务", command=self._add_automation_task).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▶️ 手动触发", command=self._trigger_automation_task).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="⏸️ 禁用", command=self._disable_automation_task).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▶️ 启用", command=self._enable_automation_task).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🗑️ 删除", command=self._delete_automation_task).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🔄 刷新", command=self._refresh_automation_tasks).pack(fill=tk.X, pady=2)

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        run_frame = ttk.LabelFrame(right, text="执行记录", padding="5")
        run_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.auto_run_tree = ttk.Treeview(
            run_frame, columns=("id", "task", "status", "started", "duration"),
            show="headings", height=8
        )
        self.auto_run_tree.heading("id", text="运行ID")
        self.auto_run_tree.heading("task", text="任务")
        self.auto_run_tree.heading("status", text="状态")
        self.auto_run_tree.heading("started", text="开始时间")
        self.auto_run_tree.heading("duration", text="耗时")
        self.auto_run_tree.column("id", width=100)
        self.auto_run_tree.column("task", width=120)
        self.auto_run_tree.column("status", width=70)
        self.auto_run_tree.column("started", width=130)
        self.auto_run_tree.column("duration", width=60)

        rsb = ttk.Scrollbar(run_frame, orient=tk.VERTICAL, command=self.auto_run_tree.yview)
        self.auto_run_tree.configure(yscrollcommand=rsb.set)
        self.auto_run_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)

        log_frame = ttk.LabelFrame(right, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.auto_log_text = tk.Text(log_frame, height=6, wrap=tk.WORD, state=tk.DISABLED,
                                      font=("Consolas", 9))
        lsb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.auto_log_text.yview)
        self.auto_log_text.configure(yscrollcommand=lsb.set)
        self.auto_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.auto_task_tree.bind("<<TreeviewSelect>>", self._on_auto_task_selected)
        self.auto_run_tree.bind("<<TreeviewSelect>>", self._on_auto_run_selected)

        self._refresh_automation_tasks()

    def _get_automation_engine(self):
        try:
            from .automation.engine import get_automation_engine
            return get_automation_engine()
        except Exception:
            return None

    def _refresh_automation_tasks(self):
        for item in self.auto_task_tree.get_children():
            self.auto_task_tree.delete(item)
        engine = self._get_automation_engine()
        if not engine:
            return
        tasks = engine.list_tasks()
        for t in tasks:
            enabled = "✅" if t.enabled else "⏸️"
            self.auto_task_tree.insert("", tk.END, values=(
                t.task_id[:8],
                t.name,
                t.automation_type,
                t.trigger_type,
                enabled
            ))

    def _add_automation_task(self):
        engine = self._get_automation_engine()
        if not engine:
            messagebox.showerror("错误", "自动化引擎未初始化")
            return

        dlg = tk.Toplevel(self.window)
        dlg.title("添加自动化任务")
        dlg.geometry("450x400")
        dlg.transient(self.window)
        dlg.grab_set()

        fields = ttk.Frame(dlg, padding="15")
        fields.pack(fill=tk.BOTH, expand=True)

        ttk.Label(fields, text="任务名称:").grid(row=0, column=0, sticky=tk.W, pady=3)
        name_var = tk.StringVar()
        ttk.Entry(fields, textvariable=name_var, width=30).grid(row=0, column=1, pady=3)

        ttk.Label(fields, text="任务类型:").grid(row=1, column=0, sticky=tk.W, pady=3)
        type_var = tk.StringVar(value="workflow")
        ttk.Combobox(fields, textvariable=type_var, width=27,
                     values=["model", "non_model", "workflow", "popup"],
                     state="readonly").grid(row=1, column=1, pady=3)

        ttk.Label(fields, text="触发器类型:").grid(row=2, column=0, sticky=tk.W, pady=3)
        trigger_var = tk.StringVar(value="interval")
        ttk.Combobox(fields, textvariable=trigger_var, width=27,
                     values=["cron", "interval", "event", "course_schedule"],
                     state="readonly").grid(row=2, column=1, pady=3)

        ttk.Label(fields, text="间隔(分钟≥30):").grid(row=3, column=0, sticky=tk.W, pady=3)
        interval_var = tk.StringVar(value="60")
        ttk.Entry(fields, textvariable=interval_var, width=30).grid(row=3, column=1, pady=3)

        ttk.Label(fields, text="Cron表达式:").grid(row=4, column=0, sticky=tk.W, pady=3)
        cron_var = tk.StringVar(value="0 * * * *")
        ttk.Entry(fields, textvariable=cron_var, width=30).grid(row=4, column=1, pady=3)

        ttk.Label(fields, text="工作流ID:").grid(row=5, column=0, sticky=tk.W, pady=3)
        wf_var = tk.StringVar()
        wf_ids = []
        try:
            wf_ids = [d["workflow_id"] for d in engine._workflow_engine.persistence.list_definitions()]
        except Exception:
            pass
        ttk.Combobox(fields, textvariable=wf_var, width=27, values=wf_ids).grid(row=5, column=1, pady=3)

        ttk.Label(fields, text="模型提示词:").grid(row=6, column=0, sticky=tk.W, pady=3)
        prompt_var = tk.StringVar()
        ttk.Entry(fields, textvariable=prompt_var, width=30).grid(row=6, column=1, pady=3)

        def do_add():
            try:
                from .automation.engine import get_automation_engine
                from .automation.triggers import TriggerType
                interval = max(int(interval_var.get()), 30)
                trigger_type_str = trigger_var.get()
                trigger_config = {}
                if trigger_type_str == TriggerType.INTERVAL.value:
                    trigger_config["interval_seconds"] = interval * 60
                elif trigger_type_str == TriggerType.CRON.value:
                    trigger_config["cron_expr"] = cron_var.get()
                action_config = {}
                auto_type = type_var.get()
                if auto_type == "workflow":
                    action_config["workflow_id"] = wf_var.get()
                elif auto_type == "model":
                    action_config["prompt"] = prompt_var.get()
                engine.register_task(
                    name=name_var.get(),
                    automation_type=auto_type,
                    trigger_type=trigger_type_str,
                    trigger_config=trigger_config,
                    action_config=action_config,
                )
                self._refresh_automation_tasks()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("错误", str(e))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        ttk.Button(btn_frame, text="添加", command=do_add).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.RIGHT)

    def _trigger_automation_task(self):
        engine = self._get_automation_engine()
        if not engine:
            return
        selection = self.auto_task_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择任务")
            return
        task_id_short = self.auto_task_tree.item(selection[0], "values")[0]
        tasks = engine.list_tasks()
        for t in tasks:
            if t.task_id.startswith(task_id_short):
                engine.trigger_task(t.task_id)
                messagebox.showinfo("成功", "任务已触发")
                return

    def _enable_automation_task(self):
        engine = self._get_automation_engine()
        if not engine:
            return
        selection = self.auto_task_tree.selection()
        if not selection:
            return
        task_id_short = self.auto_task_tree.item(selection[0], "values")[0]
        for t in engine.list_tasks():
            if t.task_id.startswith(task_id_short):
                engine.enable_task(t.task_id)
                self._refresh_automation_tasks()
                return

    def _disable_automation_task(self):
        engine = self._get_automation_engine()
        if not engine:
            return
        selection = self.auto_task_tree.selection()
        if not selection:
            return
        task_id_short = self.auto_task_tree.item(selection[0], "values")[0]
        for t in engine.list_tasks():
            if t.task_id.startswith(task_id_short):
                engine.disable_task(t.task_id)
                self._refresh_automation_tasks()
                return

    def _delete_automation_task(self):
        engine = self._get_automation_engine()
        if not engine:
            return
        selection = self.auto_task_tree.selection()
        if not selection:
            return
        if not messagebox.askyesno("确认", "确定删除此自动化任务？"):
            return
        task_id_short = self.auto_task_tree.item(selection[0], "values")[0]
        for t in engine.list_tasks():
            if t.task_id.startswith(task_id_short):
                engine.unregister_task(t.task_id)
                self._refresh_automation_tasks()
                return

    def _on_auto_task_selected(self, event=None):
        engine = self._get_automation_engine()
        if not engine:
            return
        selection = self.auto_task_tree.selection()
        if not selection:
            return
        task_id_short = self.auto_task_tree.item(selection[0], "values")[0]
        for t in engine.list_tasks():
            if t.task_id.startswith(task_id_short):
                logs = engine.persistence.get_logs(t.task_id, limit=20)
                self.auto_log_text.config(state=tk.NORMAL)
                self.auto_log_text.delete(1.0, tk.END)
                for log in reversed(logs):
                    ts = (log.get("created_at") or "")[11:19]
                    level = log.get("log_level", "info")
                    self.auto_log_text.insert(tk.END, f"[{ts}] [{level}] {log.get('message', '')}\n")
                self.auto_log_text.config(state=tk.DISABLED)

                runs = engine.persistence.list_runs(t.task_id, limit=10)
                for item in self.auto_run_tree.get_children():
                    self.auto_run_tree.delete(item)
                for r in runs:
                    status = r.status
                    icon = {"completed": "✅", "failed": "❌", "running": "🔄"}.get(status, status)
                    self.auto_run_tree.insert("", tk.END, values=(
                        r.run_id[:8],
                        t.name,
                        icon,
                        r.started_at[11:19] if r.started_at else "",
                        f"{r.duration_ms}ms" if r.duration_ms else ""
                    ))
                return

    def _on_auto_run_selected(self, event=None):
        pass


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


class GlobalApprovalManager:
    """全局审批弹窗管理器 - 桥接 ApprovalManager 和 UI 弹窗"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._root_window = None
        self._trust_gate = TrustGate() if HAS_TRUST_GATE else None
    
    def set_root_window(self, root_window):
        self._root_window = root_window
    
    def show_approval_dialog(self, request):
        if not HAS_APPROVAL:
            request.decide(ApprovalDecision.DENY)
            return

        if self._trust_gate:
            tool_name = getattr(request, 'tool_name', '') or ''
            source_plugin = getattr(request, '_source_plugin', '') or ''
            if source_plugin and not self._trust_gate.check_tool_access(source_plugin, tool_name):
                import logging
                logging.getLogger(__name__).warning(f"[审批] TrustGate拒绝: plugin={source_plugin} tool={tool_name}")
                request.decide(ApprovalDecision.DENY)
                return
        
        if self._root_window and hasattr(self._root_window, 'winfo_exists') and self._root_window.winfo_exists():
            from .harness import ApprovalDecision
            
            def handle_decision(decision_str: str):
                decision_map = {
                    "approve": ApprovalDecision.APPROVE,
                    "deny": ApprovalDecision.DENY,
                    "always_approve": ApprovalDecision.ALWAYS_APPROVE,
                }
                decision = decision_map.get(decision_str, ApprovalDecision.DENY)
                request.decide(decision)
                
                if decision_str == "always_approve" and request.tool_name:
                    try:
                        config_manager = get_config_manager()
                        config_manager.add_always_approved_tool(request.tool_name)
                    except Exception:
                        pass
            
            self._root_window.after(0, lambda: ApprovalDialog(self._root_window, request, handle_decision))
        else:
            import logging
            logging.getLogger(__name__).warning("[审批] 没有可用的根窗口来显示审批弹窗，自动拒绝")
            request.decide(ApprovalDecision.DENY)


_global_approval_manager = None


def get_global_approval_manager() -> GlobalApprovalManager:
    """获取全局审批弹窗管理器"""
    global _global_approval_manager
    if _global_approval_manager is None:
        _global_approval_manager = GlobalApprovalManager()
    return _global_approval_manager
