---
name: physics-lab
description: "物理科学实验模拟和计算助手，支持力学、电磁学、热力学、量子力学等。"
version: 1.0.0
author: TS2
platforms: [linux, macos, windows]
metadata:
  ts2:
    tags: [physics, simulation, mechanics, electromagnetism, thermodynamics, quantum]
    category: science
allowed_tools:
  - terminal
  - read_file
  - write_file
  - web_search
  - python_repl
---

# 物理实验室技能

物理科学实验模拟和计算助手，支持多种物理领域的建模、仿真和可视化。

## 使用场景

- 物理公式推导和数值计算
- 实验数据分析和拟合
- 物理过程模拟和可视化
- 物理概念教学和演示
- 论文图表生成

## 支持领域

### 经典力学
- 牛顿运动定律、拉格朗日力学、哈密顿力学
- 刚体运动、流体力学
- 天体力学轨道计算

### 电磁学
- 麦克斯韦方程组求解
- 电路分析（基尔霍夫定律）
- 电磁波传播模拟

### 热力学与统计物理
- 热力学过程计算
- 配分函数和统计分布
- 相变分析

### 量子力学
- 薛定谔方程数值求解
- 量子态演化和测量
- 量子谐振子、氢原子模型

### 光学
- 干涉衍射计算
- 薄透镜成像
- 光谱分析

## 工作流

1. **理解问题**：明确物理系统、边界条件、已知量
2. **建立模型**：选择合适的物理理论和数学工具
3. **数值计算**：使用 Python (numpy/scipy) 进行计算
4. **可视化**：使用 matplotlib 生成图表
5. **验证**：检查量纲、极限情况、守恒律

## 输出规范

- 所有数值结果标注单位和有效数字
- 图表包含坐标轴标签、图例、标题
- 公式使用 LaTeX 格式
- 代码文件保存为 `.py` 格式
