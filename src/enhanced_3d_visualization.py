#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2增强3D可视化系统
超炫酷的3D知识网络可视化
"""

import random
import math
from pathlib import Path
from typing import List, Dict, Any

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


class Enhanced3DVisualizer:
    """增强3D可视化器"""
    
    # 炫酷配色方案
    COLOR_SCHEMES = {
        'neon': ['#ff0080', '#00ffff', '#ff00ff', '#00ff00', '#ffff00', '#ff8000'],
        'cosmic': ['#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#84cc16', '#f59e0b'],
        'fire': ['#ff4444', '#ff6600', '#ff8800', '#ffaa00', '#ffcc00', '#ffff00'],
        'ocean': ['#0066ff', '#0099ff', '#00ccff', '#00ffff', '#66ffff', '#ccffff'],
    }
    
    def __init__(self):
        self.points = []
        self.connections = []
    
    def generate_spiral_3d_points(self, num_points: int = 20, base_radius: float = 3.0) -> List[Dict]:
        """生成螺旋3D点"""
        points = []
        for i in range(num_points):
            angle = i * (2 * math.pi / 5)  # 5圈螺旋
            z = (i / num_points) * 10 - 5
            radius = base_radius * (1 + 0.3 * math.sin(angle * 2))
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            points.append({
                'x': x, 'y': y, 'z': z,
                'color': self.COLOR_SCHEMES['cosmic'][i % len(self.COLOR_SCHEMES['cosmic'])],
                'size': 10 + 5 * math.sin(angle * 3),
                'label': f'知识节点 {i+1}'
            })
        self.points = points
        return points
    
    def generate_random_3d_connections(self, connection_probability: float = 0.3):
        """生成随机3D连接"""
        connections = []
        for i in range(len(self.points)):
            for j in range(i + 1, len(self.points)):
                if random.random() < connection_probability:
                    connections.append({
                        'start': i, 'end': j,
                        'color': random.choice(self.COLOR_SCHEMES['neon']),
                        'width': 1 + random.random() * 3,
                        'style': random.choice(['solid', 'dash', 'dot'])
                    })
        self.connections = connections
        return connections
    
    def create_3d_knowledge_network(self):
        """创建3D知识网络"""
        if not HAS_PLOTLY or not HAS_NUMPY:
            return None
        
        # 生成数据
        self.generate_spiral_3d_points(25, 4.0)
        self.generate_random_3d_connections(0.25)
        
        # 创建3D图形
        fig = go.Figure()
        
        # 添加连接线
        for conn in self.connections:
            p1 = self.points[conn['start']]
            p2 = self.points[conn['end']]
            fig.add_trace(go.Scatter3d(
                x=[p1['x'], p2['x']],
                y=[p1['y'], p2['y']],
                z=[p1['z'], p2['z']],
                mode='lines',
                line=dict(color=conn['color'], width=conn['width']),
                opacity=0.6
            ))
        
        # 添加节点
        x_coords = [p['x'] for p in self.points]
        y_coords = [p['y'] for p in self.points]
        z_coords = [p['z'] for p in self.points]
        colors = [p['color'] for p in self.points]
        sizes = [p['size'] for p in self.points]
        labels = [p['label'] for p in self.points]
        
        fig.add_trace(go.Scatter3d(
            x=x_coords, y=y_coords, z=z_coords,
            mode='markers+text',
            marker=dict(size=sizes, color=colors, opacity=0.9),
            text=labels,
            textposition="top center"
        ))
        
        # 添加中心核心
        fig.add_trace(go.Scatter3d(
            x=[0], y=[0], z=[0],
            mode='markers',
            marker=dict(size=30, color='#3b82f6', opacity=0.8),
            name='WS2核心'
        ))
        
        # 设置布局
        fig.update_layout(
            title=dict(
                text='🌌 WS2 3D 知识网络宇宙',
                font=dict(size=24, color='#7dd3fc'),
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
            showlegend=False,
            height=800,
            margin=dict(l=0, r=0, t=100, b=0)
        )
        
        return fig
    
    def create_flow_visualization(self):
        """创建流动可视化"""
        if not HAS_PLOTLY or not HAS_NUMPY:
            return None
        
        # 创建流动数据
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
        
        # 添加粒子点
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
        
        return fig
    
    def create_multi_panel_dashboard(self):
        """创建多面板仪表盘"""
        if not HAS_PLOTLY or not HAS_NUMPY:
            return None
        
        fig = make_subplots(
            rows=2, cols=2,
            specs=[
                [{'type': 'scene'}, {'type': 'xy'}],
                [{'type': 'xy'}, {'type': 'scene'}]
            ],
            subplot_titles=(
                '知识网络', '学习进展',
                '知识热度', '3D探索空间'
            )
        )
        
        # 1. 左上 - 简单3D网络
        self.generate_spiral_3d_points(15, 2.0)
        x = [p['x'] for p in self.points]
        y = [p['y'] for p in self.points]
        z = [p['z'] for p in self.points]
        
        fig.add_trace(
            go.Scatter3d(x=x, y=y, z=z, mode='markers', marker=dict(color='cyan', size=8)),
            row=1, col=1
        )
        
        # 2. 右上 - 学习进度条
        categories = ['数学', '物理', '计算机', '生物', '化学']
        progress = [85, 72, 93, 65, 58]
        colors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444']
        
        for cat, prog, color in zip(categories, progress, colors):
            fig.add_trace(
                go.Bar(x=[cat], y=[prog], marker=dict(color=color), name=cat),
                row=1, col=2
            )
        
        # 3. 左下 - 知识热图
        heatmap_data = np.random.rand(10, 10)
        fig.add_trace(
            go.Heatmap(z=heatmap_data, colorscale='Viridis'),
            row=2, col=1
        )
        
        # 4. 右下 - 另一个3D视图
        t = np.linspace(0, 20, 200)
        x2 = np.sin(t) * (3 + np.cos(t * 3))
        y2 = np.cos(t) * (3 + np.cos(t * 3))
        z2 = np.sin(t * 3)
        
        fig.add_trace(
            go.Scatter3d(x=x2, y=y2, z=z2, mode='lines', line=dict(width=4, color='magenta')),
            row=2, col=2
        )
        
        fig.update_layout(
            height=900,
            title_text='🚀 WS2 超酷分析仪表盘',
            title_x=0.5,
            paper_bgcolor='#0f172a',
            plot_bgcolor='#0f172a',
            font_color='#e2e8f0'
        )
        
        return fig


def launch_enhanced_visualization():
    """启动增强可视化"""
    print("🚀 启动WS2增强3D可视化系统...")
    
    viz = Enhanced3DVisualizer()
    
    # 显示选择菜单
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              WS2 增强3D可视化系统                               ║
╠═══════════════════════════════════════════════════════════════╣
║  请选择可视化类型:                                              ║
║    1. 🌌 3D知识网络宇宙                                        ║
║    2. 🌊 知识流动轨迹                                          ║
║    3. 🚀 综合分析仪表盘                                         ║
║    4. 🌟 全部展示                                              ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        choice = input("请输入选项 (1-4): ").strip()
        
        if choice == '1':
            fig = viz.create_3d_knowledge_network()
            if fig:
                fig.show()
        elif choice == '2':
            fig = viz.create_flow_visualization()
            if fig:
                fig.show()
        elif choice == '3':
            fig = viz.create_multi_panel_dashboard()
            if fig:
                fig.show()
        elif choice == '4':
            # 展示全部
            fig1 = viz.create_3d_knowledge_network()
            if fig1:
                fig1.show()
            
            fig2 = viz.create_flow_visualization()
            if fig2:
                fig2.show()
            
            fig3 = viz.create_multi_panel_dashboard()
            if fig3:
                fig3.show()
        else:
            print("❌ 无效选项，默认展示3D知识网络")
            fig = viz.create_3d_knowledge_network()
            if fig:
                fig.show()
                
    except Exception as e:
        print(f"❌ 可视化失败: {e}")
        print("💡 请确保已安装依赖: pip install plotly numpy")


if __name__ == "__main__":
    launch_enhanced_visualization()
