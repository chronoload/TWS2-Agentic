#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2世界地图式总分析系统
现代化、花哨的可视化分析界面
使用多种可视化技术展示系统的整体路线和解析能力
"""

import json
import random
import math
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Tuple, Any

# 导入现代可视化库
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch, Circle, Arrow, Rectangle
    from matplotlib.collections import LineCollection
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class WS2WorldMapAnalyzer:
    """WS2系统世界地图式可视化分析器"""
    
    # 颜色配置
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
    
    # 渐变配色方案
    GRADIENTS = {
        'ocean': ['#0c4a6e', '#0369a1', '#0284c7', '#0ea5e9', '#38bdf8', '#7dd3fc'],
        'fire': ['#7f1d1d', '#b91c1c', '#dc2626', '#ef4444', '#f87171', '#fca5a5'],
        'forest': ['#14532d', '#166534', '#15803d', '#16a34a', '#22c55e', '#4ade80'],
        'cosmic': ['#1e1b4b', '#312e81', '#3730a3', '#4f46e5', '#6366f1', '#818cf8'],
        'sunset': ['#7c2d12', '#9a3412', '#c2410c', '#ea580c', '#f97316', '#fb923c'],
    }
    
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
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.course_system = None
        self.workflow_logger = None
        self.resource_manager = None
        self.animation_counter = 0
        
    def initialize(self, course_system=None, workflow_logger=None, resource_manager=None):
        """初始化分析器"""
        self.course_system = course_system
        self.workflow_logger = workflow_logger
        self.resource_manager = resource_manager
    
    def generate_pulse_visualization(self, fig, ax, center_x, center_y, radius, color, num_pulses=3):
        """生成脉冲效果"""
        for i in range(num_pulses):
            r = radius * (1 + i * 0.3)
            alpha = 0.6 / (i + 1)
            circle = Circle((center_x, center_y), r, 
                          facecolor='none', 
                          edgecolor=color,
                          linewidth=2,
                          alpha=alpha)
            ax.add_patch(circle)
    
    def generate_dashed_line(self, ax, x1, y1, x2, y2, color, width=2, dash_pattern=(5, 3)):
        """生成虚线"""
        ax.plot([x1, x2], [y1, y2], 
               color=color, 
               linewidth=width,
               dashes=dash_pattern)
    
    def generate_solid_line(self, ax, x1, y1, x2, y2, color, width=3, arrow=True):
        """生成实线（带箭头）"""
        if arrow:
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx*dx + dy*dy)
            if length > 0:
                arrow_length = min(20, length * 0.1)
                arrow = Arrow(x1, y1, dx * 0.9, dy * 0.9, 
                            width=width * 2, color=color)
                ax.add_patch(arrow)
        else:
            ax.plot([x1, x2], [y1, y2], 
                   color=color, 
                   linewidth=width)
    
    def generate_colored_block(self, ax, x, y, width, height, color, label, alpha=0.7):
        """生成彩色块"""
        block = FancyBboxPatch((x - width/2, y - height/2), 
                             width, height,
                             boxstyle="round,pad=0.1",
                             facecolor=color,
                             edgecolor='white',
                             linewidth=2,
                             alpha=alpha)
        ax.add_patch(block)
        
        # 添加标签
        ax.text(x, y, label, 
               ha='center', va='center',
               fontsize=10, fontweight='bold',
               color='white')
    
    def create_world_map_analysis(self, canvas_width=800, canvas_height=600):
        """创建世界地图式分析图"""
        if not HAS_MATPLOTLIB:
            return None
        
        fig, ax = plt.subplots(figsize=(canvas_width/100, canvas_height/100))
        ax.set_xlim(0, canvas_width)
        ax.set_ylim(0, canvas_height)
        ax.set_aspect('equal')
        ax.axis('off')
        
        # 设置深色背景
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')
        
        # 1. 绘制中心 - WS2核心系统
        center_x, center_y = canvas_width / 2, canvas_height / 2
        self.generate_colored_block(ax, center_x, center_y, 120, 80, 
                                   self.COLORS['primary'], 'WS2 CORE')
        self.generate_pulse_visualization(ax, center_x, center_y, 40, 
                                         self.COLORS['primary'], num_pulses=4)
        
        # 2. 绘制学科领域节点
        domain_nodes = {}
        for i, (domain, (x, y)) in enumerate(self.DOMAIN_COORDS.items()):
            # 映射到画布范围
            mapped_x = center_x + (x - 250) * 1.2
            mapped_y = center_y + (y - 200) * 1.2
            
            color = list(self.COLORS.values())[i % len(self.COLORS)]
            
            # 绘制节点块
            self.generate_colored_block(ax, mapped_x, mapped_y, 80, 50, 
                                       color, domain, alpha=0.8)
            
            # 绘制连接到中心
            line_type = random.choice(['solid', 'dashed'])
            if line_type == 'solid':
                self.generate_solid_line(ax, center_x, center_y, mapped_x, mapped_y, color)
            else:
                self.generate_dashed_line(ax, center_x, center_y, mapped_x, mapped_y, color)
            
            domain_nodes[domain] = (mapped_x, mapped_y)
        
        # 3. 绘制跨学科连接
        domain_list = list(domain_nodes.keys())
        for i in range(len(domain_list)):
            for j in range(i + 1, len(domain_list)):
                if random.random() < 0.3:  # 30%概率绘制连接
                    d1, (x1, y1) = domain_list[i], domain_nodes[domain_list[i]]
                    d2, (x2, y2) = domain_list[j], domain_nodes[domain_list[j]]
                    
                    color = random.choice(list(self.COLORS.values()))
                    line_type = random.choice(['solid', 'dashed'])
                    
                    if line_type == 'solid':
                        self.generate_solid_line(ax, x1, y1, x2, y2, color, width=1, arrow=False)
                    else:
                        self.generate_dashed_line(ax, x1, y1, x2, y2, color, width=1)
        
        # 4. 添加标题
        ax.text(center_x, canvas_height - 50, 
               'WS2 SYSTEM WORLD MAP',
               ha='center', va='center',
               fontsize=24, fontweight='bold',
               color='#7dd3fc')
        
        # 5. 添加副标题
        ax.text(center_x, canvas_height - 80, 
               'Knowledge Network & Analytical Capabilities',
               ha='center', va='center',
               fontsize=14,
               color='#94a3b8')
        
        return fig
    
    def create_progress_flow_chart(self):
        """创建学习进度流程图"""
        if not HAS_PLOTLY:
            return None
        
        # 模拟数据
        stages = ['课程发现', '资源收集', '知识吸收', '笔记生成', '练习巩固', '复习回顾', '掌握应用']
        progress = [100, 85, 70, 60, 45, 30, 20]
        colors = [self.COLORS['success'], self.COLORS['info'], self.COLORS['primary'],
                 self.COLORS['secondary'], self.COLORS['warning'], self.COLORS['orange'],
                 self.COLORS['danger']]
        
        fig = go.Figure()
        
        # 绘制桑基图样式的流程
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
            title='学习进度流动图',
            plot_bgcolor='#0f172a',
            paper_bgcolor='#0f172a',
            font_color='#e2e8f0',
            showlegend=False,
            height=400,
        )
        
        fig.update_xaxes(gridcolor='#334155')
        fig.update_yaxes(gridcolor='#334155')
        
        return fig
    
    def create_knowledge_graph(self):
        """创建知识图谱"""
        if not HAS_NETWORKX or not HAS_MATPLOTLIB:
            return None
        
        G = nx.Graph()
        
        # 添加节点
        if self.course_system:
            for course in self.course_system.courses:
                domain = course.get('domain', '未知')
                G.add_node(course.get('course_title', '未知'), 
                          domain=domain,
                          type='course')
        
        # 如果没有课程数据，添加模拟数据
        if len(G.nodes) == 0:
            sample_topics = ['微积分', '线性代数', '概率论', '量子力学', 
                            '统计学习', '神经网络', '优化理论', '数值分析']
            for topic in sample_topics:
                G.add_node(topic, domain='数学', type='topic')
        
        # 添加边
        nodes = list(G.nodes)
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if random.random() < 0.4:
                    G.add_edge(nodes[i], nodes[j], weight=random.random())
        
        # 绘制
        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')
        
        pos = nx.spring_layout(G, k=0.5, iterations=50)
        
        # 绘制边
        nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.3, 
                              edge_color=self.COLORS['primary'])
        
        # 绘制节点
        nx.draw_networkx_nodes(G, pos, ax=ax, 
                              node_color=[self.COLORS['secondary']],
                              node_size=2000, alpha=0.8)
        
        # 绘制标签
        nx.draw_networkx_labels(G, pos, ax=ax, font_color='white', 
                               font_weight='bold')
        
        ax.axis('off')
        ax.set_title('知识关联图谱', color='#7dd3fc', fontsize=16, pad=20)
        
        return fig
    
    def create_analytics_dashboard(self):
        """创建综合分析仪表盘"""
        if not HAS_PLOTLY:
            return None
        
        # 创建子图
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('学习时间统计', '课程完成度', '学科分布', '学习效率'),
            specs=[[{"type": "pie"}, {"type": "bar"}],
                  [{"type": "scatter"}, {"type": "line"}]]
        )
        
        # 1. 学习时间饼图
        time_categories = ['数学', '物理', '计算机', '其他']
        time_values = [35, 25, 30, 10]
        fig.add_trace(go.Pie(
            labels=time_categories,
            values=time_values,
            marker_colors=[self.COLORS['primary'], self.COLORS['secondary'], 
                          self.COLORS['success'], self.COLORS['warning']],
            textinfo='label+percent'
        ), row=1, col=1)
        
        # 2. 课程完成度
        if self.course_system:
            course_names = [c.get('course_title', '')[:15] for c in self.course_system.courses[:5]]
            completion = [self.course_system.get_completion_pct(c.get('note_id', c.get('course_title'))) 
                        for c in self.course_system.courses[:5]]
        else:
            course_names = ['课程A', '课程B', '课程C', '课程D', '课程E']
            completion = [75, 60, 90, 45, 80]
        
        fig.add_trace(go.Bar(
            x=course_names,
            y=completion,
            marker_color=self.COLORS['primary'],
            text=[f'{c}%' for c in completion]
        ), row=1, col=2)
        
        # 3. 学科分布散点图
        if self.course_system:
            domains = [c.get('domain', '未知') for c in self.course_system.courses]
            domain_counts = Counter(domains)
            x = list(range(len(domain_counts)))
            y = list(domain_counts.values())
            labels = list(domain_counts.keys())
        else:
            labels = ['数学', '物理', '计算机', '生物', '化学']
            x = [1, 2, 3, 4, 5]
            y = [8, 6, 12, 4, 5]
        
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='markers+text',
            marker=dict(size=[s*50 for s in y], color=self.COLORS['secondary']),
            text=labels,
            textposition='top center'
        ), row=2, col=1)
        
        # 4. 学习效率折线
        days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        efficiency = [65, 78, 72, 85, 90, 75, 60]
        
        fig.add_trace(go.Scatter(
            x=days,
            y=efficiency,
            mode='lines+markers',
            line=dict(color=self.COLORS['success'], width=3),
            marker=dict(size=10, color=self.COLORS['success'])
        ), row=2, col=2)
        
        # 更新布局
        fig.update_layout(
            height=800,
            title_text='WS2 综合分析仪表盘',
            title_x=0.5,
            plot_bgcolor='#0f172a',
            paper_bgcolor='#0f172a',
            font_color='#e2e8f0',
            showlegend=False
        )
        
        return fig
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """获取分析摘要"""
        summary = {
            'total_courses': 0,
            'total_lessons': 0,
            'completed_lessons': 0,
            'total_study_time': 0,
            'domain_coverage': [],
            'learning_metrics': {}
        }
        
        if self.course_system:
            summary['total_courses'] = len(self.course_system.courses)
            summary['total_lessons'] = sum(len(c.get('lessons', [])) for c in self.course_system.courses)
            
            completed = 0
            for course in self.course_system.courses:
                cid = course.get('note_id', course.get('course_title'))
                progress = self.course_system.get_course_progress(cid)
                completed += len(progress.get('completed_lessons', []))
            summary['completed_lessons'] = completed
            
            domains = [c.get('domain', '未知') for c in self.course_system.courses]
            summary['domain_coverage'] = list(set(domains))
        
        if self.workflow_logger:
            stats = self.workflow_logger.get_stats()
            summary['total_study_time'] = stats.get('total_focus_time', 0)
            summary['learning_metrics'] = stats.get('evaluation', {})
        
        return summary


class WS2AnalysisGUI:
    """WS2分析系统GUI界面"""
    
    def __init__(self, root, base_dir: Path):
        self.root = root
        self.base_dir = base_dir
        self.analyzer = WS2WorldMapAnalyzer(base_dir)
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI界面"""
        self.root.title('WS2 世界地图式总分析系统')
        self.root.geometry('1400x900')
        
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # 左侧导航面板
        nav_frame = ttk.LabelFrame(main_frame, text="分析视图", padding="10")
        nav_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # 导航按钮
        ttk.Button(nav_frame, text="🌍 世界地图", 
                  command=self.show_world_map).grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(nav_frame, text="📊 分析仪表盘", 
                  command=self.show_dashboard).grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(nav_frame, text="🔗 知识图谱", 
                  command=self.show_knowledge_graph).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(nav_frame, text="📈 进度流程", 
                  command=self.show_progress_flow).grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # 右侧显示区域
        display_frame = ttk.LabelFrame(main_frame, text="可视化分析", padding="10")
        display_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        display_frame.columnconfigure(0, weight=1)
        display_frame.rowconfigure(0, weight=1)
        
        # 信息标签
        self.info_label = ttk.Label(display_frame, 
                                   text="选择一个分析视图开始探索...",
                                   font=('Arial', 14))
        self.info_label.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # 摘要信息
        summary_frame = ttk.LabelFrame(main_frame, text="系统摘要", padding="10")
        summary_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.summary_text = tk.Text(summary_frame, height=8, wrap=tk.WORD)
        self.summary_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # 更新摘要
        self.update_summary()
    
    def update_summary(self):
        """更新摘要信息"""
        summary = self.analyzer.get_analysis_summary()
        
        text = f"""
╔══════════════════════════════════════════════════════════════╗
║                    WS2 系统分析摘要                          ║
╠══════════════════════════════════════════════════════════════╣
║  📚 总课程数: {summary['total_courses']:>4}                                               ║
║  📖 总课时数: {summary['total_lessons']:>4}                                               ║
║  ✅ 已完成:  {summary['completed_lessons']:>4}                                               ║
║  ⏱️ 学习时间: {summary['total_study_time']/3600:.1f} 小时                                       ║
║  🎯 学科覆盖: {', '.join(summary['domain_coverage']) or '无数据'}                       ║
╚══════════════════════════════════════════════════════════════╝
        """
        
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(1.0, text)
    
    def show_world_map(self):
        """显示世界地图"""
        self.info_label.config(text="🌍 正在生成WS2世界地图...")
        
        fig = self.analyzer.create_world_map_analysis()
        if fig:
            self.display_matplotlib_figure(fig)
            self.info_label.config(text="🌍 WS2知识网络世界地图")
        else:
            self.info_label.config(text="⚠️ 需要安装matplotlib库")
    
    def show_dashboard(self):
        """显示仪表盘"""
        self.info_label.config(text="📊 正在生成分析仪表盘...")
        
        fig = self.analyzer.create_analytics_dashboard()
        if fig:
            self.display_plotly_figure(fig)
            self.info_label.config(text="📊 综合分析仪表盘")
        else:
            self.info_label.config(text="⚠️ 需要安装plotly库")
    
    def show_knowledge_graph(self):
        """显示知识图谱"""
        self.info_label.config(text="🔗 正在生成知识图谱...")
        
        fig = self.analyzer.create_knowledge_graph()
        if fig:
            self.display_matplotlib_figure(fig)
            self.info_label.config(text="🔗 知识关联图谱")
        else:
            self.info_label.config(text="⚠️ 需要安装networkx和matplotlib库")
    
    def show_progress_flow(self):
        """显示进度流程"""
        self.info_label.config(text="📈 正在生成进度流程图...")
        
        fig = self.analyzer.create_progress_flow_chart()
        if fig:
            self.display_plotly_figure(fig)
            self.info_label.config(text="📈 学习进度流动图")
        else:
            self.info_label.config(text="⚠️ 需要安装plotly库")
    
    def display_matplotlib_figure(self, fig):
        """显示matplotlib图形"""
        # 创建新窗口显示图形
        top = tk.Toplevel(self.root)
        top.title("WS2 可视化分析")
        top.geometry("1000x800")
        
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def display_plotly_figure(self, fig):
        """显示plotly图形"""
        # 在浏览器中显示
        fig.show()


if __name__ == "__main__":
    BASE_DIR = Path(__file__).parent
    
    root = tk.Tk()
    app = WS2AnalysisGUI(root, BASE_DIR)
    root.mainloop()
