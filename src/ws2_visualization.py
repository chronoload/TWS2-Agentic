#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 可视化分析模块 - 提供内部调用接口
集成到WS2主程序内部，无需独立启动
"""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Callable
import random
import math

# 导入现代可视化库（可选依赖）
try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Circle, Arrow
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


class WS2Visualizer:
    """WS2 可视化分析器 - 提供内部调用接口"""
    
    # 学科领域地图坐标
    DOMAIN_COORDS = {
        '数学': (100, 100),
        '物理': (200, 80),
        '化学': (300, 120),
        '生物': (400, 100),
        '计算机科学': (150, 200),
        '人工智能': (250, 220),
        '数据科学': (350, 180),
        '工程': (450, 200),
        '经济学': (100, 300),
        '哲学': (200, 280),
        '心理学': (300, 320),
        '社会学': (400, 300),
    }
    
    # 配色方案
    COLORS = {
        'primary': '#3b82f6',
        'secondary': '#8b5cf6',
        'success': '#10b981',
        'warning': '#f59e0b',
        'danger': '#ef4444',
        'info': '#06b6d4',
        'purple': '#a855f7',
        'pink': '#ec4899',
        'cyan': '#06b6d4',
        'teal': '#14b8a6',
        'lime': '#84cc16',
        'amber': '#f59e0b',
        'orange': '#f97316',
        'red': '#ef4444',
        'sky': '#0ea5e9',
        'violet': '#8b5cf6',
    }
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.course_system = None
        self.workflow_logger = None
    
    def initialize(self, course_system=None, workflow_logger=None):
        """从WS2主程序初始化数据连接"""
        self.course_system = course_system
        self.workflow_logger = workflow_logger
    
    def create_integrated_ui(self, parent_frame):
        """创建集成到WS2主程序的UI界面
        
        Args:
            parent_frame: 父容器（Tkinter Frame）
        """
        # 清空父容器
        for widget in parent_frame.winfo_children():
            widget.destroy()
        
        # 创建可视化选项界面
        main_container = ttk.Frame(parent_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 标题
        title_frame = ttk.Frame(main_container)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(title_frame, text="🌌 WS2 可视化分析中心", 
                 font=("", 18, "bold")).pack(side=tk.LEFT)
        
        status_text = "✓ 全部可视化库就绪" if HAS_MATPLOTLIB and HAS_PLOTLY else "⚠️ 部分可视化库未安装"
        ttk.Label(title_frame, text=status_text, 
                 foreground="green" if HAS_MATPLOTLIB and HAS_PLOTLY else "orange").pack(side=tk.RIGHT)
        
        # 可视化选项网格
        grid_frame = ttk.Frame(main_container)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # 定义可视化选项
        viz_options = [
            ("🌍 世界地图", self._show_world_map, 
             "知识网络地图（Matplotlib）", HAS_MATPLOTLIB),
            ("📊 分析仪表盘", self._show_dashboard, 
             "综合分析（Plotly）", HAS_PLOTLY),
            ("🔗 知识图谱", self._show_knowledge_graph, 
             "网络关系图（NetworkX）", HAS_NETWORKX and HAS_MATPLOTLIB),
            ("📈 进度流动", self._show_progress_flow, 
             "学习进度图表（Plotly）", HAS_PLOTLY),
            ("🌌 3D知识宇宙", self._show_3d_universe, 
             "3D螺旋知识网络（Plotly）", HAS_PLOTLY),
            ("🌊 知识流动轨迹", self._show_flow_trajectory, 
             "3D知识流动（Plotly）", HAS_PLOTLY),
        ]
        
        # 创建按钮网格
        for i, (title, callback, description, available) in enumerate(viz_options):
            row, col = divmod(i, 2)
            
            card_frame = ttk.LabelFrame(grid_frame, text=title, padding=15)
            card_frame.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
            
            ttk.Label(card_frame, text=description, wraplength=250).pack(pady=(0, 15))
            
            btn = ttk.Button(card_frame, text="🚀 启动", 
                           command=callback)
            btn.pack(fill=tk.X)
            
            if not available:
                btn.config(state="disabled")
                ttk.Label(card_frame, text="⚠️ 需要安装依赖库", 
                         foreground="orange", font=("", 8)).pack(pady=5)
        
        # 配置网格
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, weight=1)
        grid_frame.rowconfigure(2, weight=1)
        
        # 底部帮助区域
        help_frame = ttk.LabelFrame(main_container, text="📖 使用帮助", padding=10)
        help_frame.pack(fill=tk.X, pady=(15, 0))
        
        help_text = (
            "• 世界地图：展示知识网络连接（实线/虚线连接）\n"
            "• 分析仪表盘：多维度学习数据统计\n"
            "• 知识图谱：学科间关联关系可视化\n"
            "• 3D宇宙：螺旋知识网络宇宙视图\n"
            "• 依赖库：建议安装 matplotlib, plotly, networkx"
        )
        ttk.Label(help_frame, text=help_text, justify=tk.LEFT).pack(anchor=tk.W)
    
    def _show_world_map(self):
        """显示2D世界地图"""
        if not HAS_MATPLOTLIB:
            messagebox.showerror("错误", "需要安装 matplotlib\npip install matplotlib")
            return
        
        top = tk.Toplevel()
        top.title("🌍 WS2 世界地图")
        top.geometry("1000x800")
        
        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')
        ax.set_xlim(0, 800)
        ax.set_ylim(0, 600)
        ax.set_aspect('equal')
        ax.axis('off')
        
        center_x, center_y = 400, 300
        
        # 中心脉冲效果
        for i in range(4):
            r = 40 * (1 + i * 0.3)
            alpha = 0.6 / (i + 1)
            circle = Circle((center_x, center_y), r, 
                          facecolor='none', edgecolor=self.COLORS['primary'],
                          linewidth=2, alpha=alpha)
            ax.add_patch(circle)
        
        # WS2核心块
        core_block = FancyBboxPatch((center_x-60, center_y-40), 120, 80,
                                   boxstyle="round,pad=0.1",
                                   facecolor=self.COLORS['primary'],
                                   edgecolor='white', linewidth=2, alpha=0.9)
        ax.add_patch(core_block)
        ax.text(center_x, center_y, "WS2 CORE", ha='center', va='center',
               fontsize=14, fontweight='bold', color='white')
        
        # 绘制学科节点
        color_list = list(self.COLORS.values())
        domain_nodes = {}
        
        for idx, (domain, (x, y)) in enumerate(self.DOMAIN_COORDS.items()):
            mapped_x = center_x + (x - 250) * 1.2
            mapped_y = center_y + (y - 200) * 1.2
            color = color_list[idx % len(color_list)]
            
            # 绘制节点块
            block = FancyBboxPatch((mapped_x-40, mapped_y-25), 80, 50,
                                  boxstyle="round,pad=0.1",
                                  facecolor=color, edgecolor='white',
                                  linewidth=2, alpha=0.8)
            ax.add_patch(block)
            ax.text(mapped_x, mapped_y, domain, ha='center', va='center',
                   fontsize=10, fontweight='bold', color='white')
            
            # 绘制到中心的连线
            line_type = random.choice(['solid', 'dashed'])
            if line_type == 'solid':
                dx = mapped_x - center_x
                dy = mapped_y - center_y
                arrow = Arrow(center_x, center_y, dx*0.9, dy*0.9,
                            width=8, color=color)
                ax.add_patch(arrow)
            else:
                ax.plot([center_x, mapped_x], [center_y, mapped_y],
                       color=color, linewidth=2, dashes=(5, 3))
            
            domain_nodes[domain] = (mapped_x, mapped_y)
        
        # 绘制跨学科连接
        domain_list = list(domain_nodes.keys())
        for i in range(len(domain_list)):
            for j in range(i + 1, len(domain_list)):
                if random.random() < 0.25:
                    x1, y1 = domain_nodes[domain_list[i]]
                    x2, y2 = domain_nodes[domain_list[j]]
                    color = random.choice(color_list)
                    line_type = random.choice(['solid', 'dashed'])
                    
                    if line_type == 'solid':
                        ax.plot([x1, x2], [y1, y2], color=color, linewidth=1.5)
                    else:
                        ax.plot([x1, x2], [y1, y2], color=color,
                               linewidth=1, dashes=(3, 2))
        
        # 添加标题
        ax.text(center_x, 560, "WS2 SYSTEM WORLD MAP",
               ha='center', va='center', fontsize=20, fontweight='bold',
               color='#7dd3fc')
        ax.text(center_x, 530, "Knowledge Network & Analytical Capabilities",
               ha='center', va='center', fontsize=12, color='#94a3b8')
        
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _show_dashboard(self):
        """显示综合分析仪表盘"""
        if not HAS_PLOTLY:
            messagebox.showerror("错误", "需要安装 plotly\npip install plotly")
            return
        
        fig = self._create_dashboard_figure()
        fig.show()
    
    def _create_dashboard_figure(self):
        """创建仪表盘Figure"""
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('📚 学习时间统计', '✅ 课程完成度',
                           '🎯 学科分布', '📈 学习效率'),
            specs=[[{"type": "pie"}, {"type": "bar"}],
                  [{"type": "scatter"}, {"type": "line"}]]
        )
        
        # 1. 学习时间饼图
        categories = ['数学', '物理', '计算机', '其他']
        values = [35, 25, 30, 10]
        colors = [self.COLORS['primary'], self.COLORS['secondary'],
                 self.COLORS['success'], self.COLORS['warning']]
        fig.add_trace(go.Pie(labels=categories, values=values,
                           marker_colors=colors, textinfo='label+percent'),
                     row=1, col=1)
        
        # 2. 课程完成度
        if self.course_system:
            course_names = [c.get('course_title', '')[:15] 
                          for c in self.course_system.courses[:5]]
            completion = [self.course_system.get_completion_pct(
                         c.get('note_id', c.get('course_title')))
                        for c in self.course_system.courses[:5]]
        else:
            course_names = ['课程A', '课程B', '课程C', '课程D', '课程E']
            completion = [75, 60, 90, 45, 80]
        
        fig.add_trace(go.Bar(x=course_names, y=completion,
                           marker_color=self.COLORS['primary'],
                           text=[f'{c}%' for c in completion]),
                     row=1, col=2)
        
        # 3. 学科分布
        import numpy as np
        if self.course_system:
            domains = [c.get('domain', '未知') for c in self.course_system.courses]
            from collections import Counter
            domain_counts = Counter(domains)
            x = list(range(len(domain_counts)))
            y = list(domain_counts.values())
            labels = list(domain_counts.keys())
        else:
            labels = ['数学', '物理', '计算机', '生物', '化学']
            x = [1, 2, 3, 4, 5]
            y = [8, 6, 12, 4, 5]
        
        fig.add_trace(go.Scatter(x=x, y=y, mode='markers+text',
                              marker=dict(size=[s*50 for s in y],
                                         color=self.COLORS['secondary']),
                              text=labels, textposition='top center'),
                     row=2, col=1)
        
        # 4. 学习效率
        days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        efficiency = [65, 78, 72, 85, 90, 75, 60]
        fig.add_trace(go.Scatter(x=days, y=efficiency,
                              mode='lines+markers',
                              line=dict(color=self.COLORS['success'], width=3),
                              marker=dict(size=10, color=self.COLORS['success'])),
                     row=2, col=2)
        
        fig.update_layout(
            height=800,
            title_text='🚀 WS2 综合分析仪表盘',
            title_x=0.5,
            plot_bgcolor='#0f172a',
            paper_bgcolor='#0f172a',
            font_color='#e2e8f0',
            showlegend=False
        )
        
        return fig
    
    def _show_knowledge_graph(self):
        """显示知识图谱"""
        if not HAS_NETWORKX or not HAS_MATPLOTLIB:
            messagebox.showerror("错误", "需要安装 networkx 和 matplotlib\n"
                                     "pip install networkx matplotlib")
            return
        
        top = tk.Toplevel()
        top.title("🔗 WS2 知识图谱")
        top.geometry("1000x800")
        
        G = nx.Graph()
        
        # 添加节点
        if self.course_system:
            for course in self.course_system.courses:
                title = course.get('course_title', '未知')
                domain = course.get('domain', '未知')
                G.add_node(title, domain=domain)
        else:
            sample_nodes = ['微积分', '线性代数', '概率论', '量子力学',
                           '统计学习', '神经网络', '优化理论', '数值分析']
            for node in sample_nodes:
                G.add_node(node, domain='数学')
        
        # 添加边
        nodes = list(G.nodes())
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if random.random() < 0.4:
                    G.add_edge(nodes[i], nodes[j], weight=random.random())
        
        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')
        ax.axis('off')
        
        pos = nx.spring_layout(G, k=0.5, iterations=50)
        
        nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.3,
                              edge_color=self.COLORS['primary'])
        nx.draw_networkx_nodes(G, pos, ax=ax,
                             node_color=[self.COLORS['secondary']],
                             node_size=2000, alpha=0.8)
        nx.draw_networkx_labels(G, pos, ax=ax, font_color='white',
                               font_weight='bold')
        
        ax.set_title('🔗 WS2 知识关联图谱', color='#7dd3fc',
                    fontsize=16, pad=20)
        
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _show_progress_flow(self):
        """显示进度流动图"""
        if not HAS_PLOTLY:
            messagebox.showerror("错误", "需要安装 plotly\npip install plotly")
            return
        
        stages = ['课程发现', '资源收集', '知识吸收', '笔记生成',
                 '练习巩固', '复习回顾', '掌握应用']
        progress = [100, 85, 70, 60, 45, 30, 20]
        colors = [self.COLORS['success'], self.COLORS['info'],
                 self.COLORS['primary'], self.COLORS['secondary'],
                 self.COLORS['warning'], self.COLORS['orange'],
                 self.COLORS['danger']]
        
        fig = go.Figure()
        for i in range(len(stages)):
            fig.add_trace(go.Bar(
                x=[stages[i]],
                y=[progress[i]],
                marker_color=colors[i],
                name=stages[i],
                text=[f'{progress[i]}%'],
                textposition='auto',
            ))
        
        fig.update_layout(
            title='📈 WS2 学习进度流动图',
            plot_bgcolor='#0f172a',
            paper_bgcolor='#0f172a',
            font_color='#e2e8f0',
            showlegend=False,
            height=500,
        )
        fig.update_xaxes(gridcolor='#334155')
        fig.update_yaxes(gridcolor='#334155')
        
        fig.show()
    
    def _show_3d_universe(self):
        """显示3D知识宇宙"""
        if not HAS_PLOTLY:
            messagebox.showerror("错误", "需要安装 plotly\npip install plotly")
            return
        
        import numpy as np
        
        n_points = 25
        t = np.linspace(0, 8 * np.pi, n_points)
        z = np.linspace(-5, 5, n_points)
        r = 4 * (1 + 0.3 * np.sin(t * 2))
        x = r * np.cos(t)
        y = r * np.sin(t)
        
        fig = go.Figure()
        
        color_list = list(self.COLORS.values())
        
        # 添加连线
        for i in range(n_points):
            for j in range(i + 1, n_points):
                if random.random() < 0.25:
                    color = random.choice(color_list)
                    fig.add_trace(go.Scatter3d(
                        x=[x[i], x[j]], y=[y[i], y[j]], z=[z[i], z[j]],
                        mode='lines',
                        line=dict(color=color, width=2),
                        opacity=0.6,
                        showlegend=False
                    ))
        
        # 添加节点
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode='markers+text',
            marker=dict(
                size=[10 + 5 * np.sin(t[i] * 3) for i in range(n_points)],
                color=[color_list[i % len(color_list)] for i in range(n_points)],
                opacity=0.9
            ),
            text=[f'知识节点 {i+1}' for i in range(n_points)],
            textposition='top center',
            showlegend=False
        ))
        
        # 中心核心
        fig.add_trace(go.Scatter3d(
            x=[0], y=[0], z=[0],
            mode='markers',
            marker=dict(size=30, color=self.COLORS['primary'], opacity=0.8),
            name='WS2核心'
        ))
        
        fig.update_layout(
            title=dict(
                text='🌌 WS2 3D 知识网络宇宙',
                font=dict(size=20, color='#7dd3fc'),
                x=0.5
            ),
            scene=dict(
                xaxis_title='维度 X',
                yaxis_title='维度 Y',
                zaxis_title='维度 Z',
                xaxis=dict(showbackground=False, showgrid=False),
                yaxis=dict(showbackground=False, showgrid=False),
                zaxis=dict(showbackground=False, showgrid=False),
                bgcolor='#0f172a'
            ),
            paper_bgcolor='#0f172a',
            height=800
        )
        
        fig.show()
    
    def _show_flow_trajectory(self):
        """显示知识流动轨迹"""
        if not HAS_PLOTLY:
            messagebox.showerror("错误", "需要安装 plotly\npip install plotly")
            return
        
        import numpy as np
        
        t = np.linspace(0, 10, 100)
        x = np.sin(t) * np.cos(t * 2)
        y = np.sin(t) * np.sin(t * 2)
        z = np.cos(t)
        
        fig = go.Figure()
        
        # 主流动轨迹
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode='lines',
            line=dict(width=8, color=np.linspace(0, 1, 100), colorscale='Viridis'),
            name='知识流动'
        ))
        
        # 粒子点
        fig.add_trace(go.Scatter3d(
            x=x[::5], y=y[::5], z=z[::5],
            mode='markers',
            marker=dict(size=12, color='cyan', opacity=0.8),
            name='知识粒子'
        ))
        
        fig.update_layout(
            title='🌊 WS2 知识流动轨迹',
            scene=dict(bgcolor='#0f172a'),
            paper_bgcolor='#0f172a',
            height=700
        )
        
        fig.show()


# ============ 导出函数 - 供WS2主程序调用 ============

def create_visualizer(base_dir: Optional[Path] = None) -> WS2Visualizer:
    """创建WS2可视化器实例
    
    这是WS2主程序调用的主入口点
    """
    return WS2Visualizer(base_dir)


def show_visualization_ui(parent_frame, visualizer: Optional[WS2Visualizer] = None):
    """在指定框架内显示可视化UI
    
    这是集成到主程序的便捷函数
    """
    if visualizer is None:
        visualizer = WS2Visualizer()
    visualizer.create_integrated_ui(parent_frame)
