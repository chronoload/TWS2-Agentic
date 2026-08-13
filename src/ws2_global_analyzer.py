#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 世界地图式总分析系统
World Map Style TS2 Global Analysis System
采用现代可视化技术展示WS2系统的整体路线和解析能力
"""

import json
import math
import random
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from typing import Dict, List, Tuple, Any, Optional


class WS2WorldMapAnalyzer:
    """WS2世界地图式分析器核心"""
    
    # 学科领域颜色映射（基于光谱色系）
    DOMAIN_COLORS = {
        "MATHEMATICS": "#FF6B6B",      # 红色
        "PHYSICS": "#4ECDC4",          # 青色
        "COMPUTER_SCIENCE": "#45B7D1", # 蓝色
        "BIOLOGY": "#96CEB4",          # 绿色
        "CHEMISTRY": "#FFEAA7",        # 黄色
        "ECONOMICS": "#DDA0DD",        # 紫色
        "PHILOSOPHY": "#F39C12",       # 橙色
        "HISTORY": "#E74C3C",          # 深红
        "LITERATURE": "#1ABC9C",       # 青绿色
        "ART": "#9B59B6",              # 深紫
        "UNKNOWN": "#95A5A6",          # 灰色
    }
    
    # 连接类型样式
    CONNECTION_STYLES = {
        "prerequisite": {"style": "dashed", "width": 2, "color": "#E74C3C"},
        "related": {"style": "solid", "width": 1, "color": "#3498DB"},
        "hierarchical": {"style": "dotted", "width": 3, "color": "#2ECC71"},
        "cross_domain": {"style": "double", "width": 4, "color": "#F39C12"},
    }
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.knowledge_graph = self._build_knowledge_graph()
        self.course_system = None
        self.progress_data = None
        
    def _build_knowledge_graph(self) -> Dict:
        """构建知识图谱"""
        return {
            "nodes": [],
            "edges": [],
            "domains": [],
        }
    
    def load_course_system(self, course_system):
        """加载课程系统数据"""
        self.course_system = course_system
        self._transform_courses_to_graph()
    
    def _transform_courses_to_graph(self):
        """将课程数据转换为图结构"""
        if not self.course_system:
            return
            
        courses = self.course_system.courses
        domain_nodes = defaultdict(list)
        
        # 构建课程节点
        for idx, course in enumerate(courses):
            domain = course.get("domain", "UNKNOWN")
            course_id = course.get("note_id", course.get("course_title", f"course_{idx}"))
            
            # 计算极坐标位置
            angle = (idx / len(courses)) * 2 * math.pi if courses else 0
            radius = self._calculate_radius_by_domain(domain, idx, len(courses))
            
            node = {
                "id": course_id,
                "type": "course",
                "title": course.get("course_title", "Unknown"),
                "domain": domain,
                "x": radius * math.cos(angle),
                "y": radius * math.sin(angle),
                "size": self._calculate_node_size(course),
                "color": self.DOMAIN_COLORS.get(domain, self.DOMAIN_COLORS["UNKNOWN"]),
                "lessons_count": len(course.get("lessons", [])),
                "progress": self._get_course_progress(course_id),
                "total_hours": course.get("total_hours", 0),
            }
            
            self.knowledge_graph["nodes"].append(node)
            domain_nodes[domain].append(node)
        
        # 添加领域中心节点
        self._add_domain_centers(domain_nodes)
        
        # 构建连接边
        self._build_edges(courses, domain_nodes)
    
    def _calculate_radius_by_domain(self, domain: str, index: int, total: int) -> float:
        """根据领域计算节点半径"""
        base_radius = 3.0
        domain_offset = {
            "MATHEMATICS": 0,
            "PHYSICS": 0.5,
            "COMPUTER_SCIENCE": 1.0,
            "BIOLOGY": 1.5,
            "CHEMISTRY": 2.0,
            "ECONOMICS": 2.5,
        }
        
        return base_radius + domain_offset.get(domain, 1.5) + (index % 3) * 0.3
    
    def _calculate_node_size(self, course: Dict) -> float:
        """计算节点大小（基于课程重要性）"""
        base_size = 10
        lessons_count = len(course.get("lessons", []))
        hours = course.get("total_hours", 0)
        
        size = base_size + math.sqrt(lessons_count) * 2 + (hours / 10 if hours else 0)
        return min(size, 30)
    
    def _get_course_progress(self, course_id: str) -> float:
        """获取课程进度"""
        if not self.course_system:
            return 0.0
            
        progress = self.course_system.get_course_progress(course_id)
        completed = len(progress.get("completed_lessons", []))
        course = self.course_system.get_course_by_id(course_id)
        
        if course and course.get("lessons"):
            total = len(course["lessons"])
            return completed / total if total > 0 else 0.0
            
        return 0.0
    
    def _add_domain_centers(self, domain_nodes: Dict):
        """添加领域中心节点"""
        for domain_idx, (domain, nodes) in enumerate(domain_nodes.items()):
            if not nodes:
                continue
                
            # 计算领域中心点位置
            avg_x = sum(n["x"] for n in nodes) / len(nodes)
            avg_y = sum(n["y"] for n in nodes) / len(nodes)
            
            center_node = {
                "id": f"domain_{domain}",
                "type": "domain_center",
                "title": domain,
                "domain": domain,
                "x": avg_x,
                "y": avg_y,
                "size": 25,
                "color": self.DOMAIN_COLORS.get(domain, self.DOMAIN_COLORS["UNKNOWN"]),
                "courses_count": len(nodes),
                "is_pulse": True,
            }
            
            self.knowledge_graph["nodes"].append(center_node)
            self.knowledge_graph["domains"].append(domain)
    
    def _build_edges(self, courses: List, domain_nodes: Dict):
        """构建连接边"""
        # 先修关系
        for course in courses:
            course_id = course.get("note_id", course.get("course_title"))
            prereqs = course.get("prerequisites", [])
            
            for prereq in prereqs:
                prereq_id = prereq.get("course_id", prereq.get("title", ""))
                if prereq_id:
                    edge = {
                        "source": prereq_id,
                        "target": course_id,
                        "type": "prerequisite",
                        "style": self.CONNECTION_STYLES["prerequisite"],
                    }
                    self.knowledge_graph["edges"].append(edge)
        
        # 同领域内课程连接
        for domain, nodes in domain_nodes.items():
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    # 随机添加一些连接（模拟知识关联性）
                    if random.random() < 0.3:
                        edge = {
                            "source": nodes[i]["id"],
                            "target": nodes[j]["id"],
                            "type": "related",
                            "style": self.CONNECTION_STYLES["related"],
                        }
                        self.knowledge_graph["edges"].append(edge)
        
        # 跨领域连接
        domains = list(domain_nodes.keys())
        for i in range(len(domains)):
            for j in range(i + 1, len(domains)):
                if random.random() < 0.4:
                    source_domain = domains[i]
                    target_domain = domains[j]
                    
                    source_node = domain_nodes[source_domain][0] if domain_nodes[source_domain] else None
                    target_node = domain_nodes[target_domain][0] if domain_nodes[target_domain] else None
                    
                    if source_node and target_node:
                        edge = {
                            "source": source_node["id"],
                            "target": target_node["id"],
                            "type": "cross_domain",
                            "style": self.CONNECTION_STYLES["cross_domain"],
                        }
                        self.knowledge_graph["edges"].append(edge)
    
    def generate_analysis_report(self) -> Dict:
        """生成分析报告"""
        if not self.course_system:
            return {}
            
        total_lessons, completed_lessons = self.course_system.get_overall_progress()
        domain_stats = self.course_system.get_domain_stats()
        
        report = {
            "summary": {
                "total_courses": len(self.course_system.courses),
                "total_lessons": total_lessons,
                "completed_lessons": completed_lessons,
                "completion_rate": (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0,
                "total_hours": self.course_system.total_hours,
            },
            "domains": domain_stats,
            "generated_at": datetime.now().isoformat(),
        }
        
        return report
    
    def export_graph_data(self, output_path: Path = None) -> Path:
        """导出图数据"""
        if output_path is None:
            output_path = self.base_dir / "ws2_analysis" / "knowledge_graph.json"
            
        output_path.parent.mkdir(exist_ok=True)
        
        export_data = {
            "graph": self.knowledge_graph,
            "report": self.generate_analysis_report(),
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
            
        return output_path


try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Arrow, FancyArrowPatch
    from matplotlib.colors import LinearSegmentedColormap
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class WS2Visualizer:
    """WS2世界地图式可视化器"""
    
    def __init__(self, analyzer: WS2WorldMapAnalyzer):
        self.analyzer = analyzer
        
    def create_interactive_visualization(self, output_path: Path = None):
        """创建交互式可视化"""
        if not PLOTLY_AVAILABLE:
            return self._create_matplotlib_visualization(output_path)
            
        return self._create_plotly_visualization(output_path)
    
    def _create_plotly_visualization(self, output_path: Path = None):
        """使用Plotly创建交互式可视化"""
        graph = self.analyzer.knowledge_graph
        nodes = graph["nodes"]
        edges = graph["edges"]
        
        # 节点轨迹
        node_x = [n["x"] for n in nodes]
        node_y = [n["y"] for n in nodes]
        node_text = [f"{n['title']}<br>领域: {n['domain']}<br>进度: {n.get('progress', 0):.1%}" for n in nodes]
        node_sizes = [n["size"] * 3 for n in nodes]
        node_colors = [n["color"] for n in nodes]
        
        # 边轨迹
        edge_x = []
        edge_y = []
        for edge in edges:
            source_node = next((n for n in nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            
            if source_node and target_node:
                edge_x.extend([source_node["x"], target_node["x"], None])
                edge_y.extend([source_node["y"], target_node["y"], None])
        
        # 创建图形
        fig = go.Figure()
        
        # 添加边
        fig.add_trace(go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=1, color='#888'),
            hoverinfo='none',
            mode='lines',
            name='连接关系'
        ))
        
        # 添加节点
        fig.add_trace(go.Scatter(
            x=node_x,
            y=node_y,
            mode='markers+text',
            hoverinfo='text',
            marker=dict(
                showscale=False,
                colorscale='Viridis',
                size=node_sizes,
                color=node_colors,
                line_width=2,
                line_color='white',
            ),
            text=[n.get("title", "")[:15] + "..." if len(n.get("title", "")) > 15 else n.get("title", "") for n in nodes],
            textposition="top center",
            name='课程/领域',
            hovertext=node_text,
        ))
        
        # 添加脉冲效果（模拟动画）
        pulse_nodes = [n for n in nodes if n.get("is_pulse", False)]
        if pulse_nodes:
            pulse_x = [n["x"] for n in pulse_nodes]
            pulse_y = [n["y"] for n in pulse_nodes]
            
            for scale in [1, 1.5, 2]:
                fig.add_trace(go.Scatter(
                    x=pulse_x,
                    y=pulse_y,
                    mode='markers',
                    marker=dict(
                        size=[n["size"] * scale * 3 for n in pulse_nodes],
                        color=[n["color"] for n in pulse_nodes],
                        opacity=1/scale,
                        line_width=0,
                    ),
                    name=f'脉冲效果 {scale}x',
                    showlegend=False,
                ))
        
        # 布局配置
        fig.update_layout(
            title='WS2 知识图谱 - 世界地图式总览',
            title_font_size=24,
            showlegend=True,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=800,
            width=1200,
            paper_bgcolor='rgb(10, 14, 39)',
            plot_bgcolor='rgb(10, 14, 39)',
            font=dict(color='white'),
        )
        
        if output_path:
            output_path.parent.mkdir(exist_ok=True)
            fig.write_html(output_path)
            
        return fig
    
    def _create_matplotlib_visualization(self, output_path: Path = None):
        """使用Matplotlib创建可视化"""
        if not MATPLOTLIB_AVAILABLE:
            return None
            
        graph = self.analyzer.knowledge_graph
        nodes = graph["nodes"]
        edges = graph["edges"]
        
        fig, ax = plt.subplots(figsize=(16, 12), facecolor='#0a0e27')
        ax.set_facecolor('#0a0e27')
        
        # 绘制边
        for edge in edges:
            source_node = next((n for n in nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            
            if source_node and target_node:
                style = edge.get("style", {})
                linestyle = '--' if style.get("style") == "dashed" else ':' if style.get("style") == "dotted" else '-'
                
                ax.plot(
                    [source_node["x"], target_node["x"]],
                    [source_node["y"], target_node["y"]],
                    color=style.get("color", "#888"),
                    linestyle=linestyle,
                    linewidth=style.get("width", 1),
                    alpha=0.6,
                )
        
        # 绘制节点
        for node in nodes:
            size = node["size"] * 50
            color = node["color"]
            
            # 脉冲效果
            if node.get("is_pulse", False):
                for i, scale in enumerate([1, 1.3, 1.6]):
                    circle = Circle(
                        (node["x"], node["y"]),
                        size/200 * scale,
                        color=color,
                        alpha=0.3 - i*0.1,
                        fill=False,
                        linewidth=2,
                    )
                    ax.add_patch(circle)
            
            # 主节点
            circle = Circle(
                (node["x"], node["y"]),
                size/200,
                color=color,
                alpha=0.8,
            )
            ax.add_patch(circle)
            
            # 标签
            ax.text(
                node["x"],
                node["y"] + size/150,
                node.get("title", "")[:12],
                ha='center',
                va='bottom',
                color='white',
                fontsize=8,
            )
        
        # 设置坐标轴
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title('WS2 知识图谱 - 世界地图式总览', color='white', fontsize=20, pad=20)
        
        if output_path:
            output_path.parent.mkdir(exist_ok=True)
            plt.savefig(output_path, facecolor='#0a0e27', edgecolor='none', dpi=150, bbox_inches='tight')
            
        return fig
    
    def create_progress_dashboard(self, output_path: Path = None):
        """创建进度仪表板"""
        if not PLOTLY_AVAILABLE:
            return None
            
        report = self.analyzer.generate_analysis_report()
        
        # 主仪表板
        fig = go.Figure()
        
        # 完成度指标
        summary = report.get("summary", {})
        completion_rate = summary.get("completion_rate", 0)
        
        # 环形进度图
        fig.add_trace(go.Indicator(
            mode="gauge+number+delta",
            value=completion_rate,
            domain={'x': [0, 0.5], 'y': [0.5, 1]},
            title={'text': "总体进度", 'font': {'size': 24}},
            delta={'reference': 0, 'increasing': {'color': "RebeccaPurple"}},
            gauge={
                'axis': {'range': [None, 100], 'tickwidth': 1,