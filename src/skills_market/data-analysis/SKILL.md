---
name: data-analysis
description: "数据分析与可视化技能，支持统计建模、机器学习、数据清洗和可视化。"
version: 1.0.0
author: TS2
platforms: [linux, macos, windows]
metadata:
  ts2:
    tags: [data, analysis, statistics, visualization, machine-learning, pandas, matplotlib]
    category: science
allowed_tools:
  - terminal
  - read_file
  - write_file
  - web_search
  - python_repl
---

# 数据分析技能

系统化的数据分析工作流，从数据获取到洞察输出。

## 使用场景

- 实验数据处理和分析
- 统计假设检验
- 数据可视化和报告生成
- 机器学习建模
- 时间序列分析

## 工作流

### 1. 数据获取
- 读取 CSV/Excel/JSON 文件
- 数据库查询
- API 数据获取

### 2. 数据清洗
- 缺失值处理
- 异常值检测
- 数据类型转换
- 重复值处理

### 3. 探索性分析 (EDA)
- 描述性统计
- 分布分析
- 相关性分析
- 分组聚合

### 4. 建模分析
- 回归分析（线性/非线性）
- 分类模型
- 聚类分析
- 时间序列预测

### 5. 可视化输出
- 静态图表（matplotlib/seaborn）
- 交互式图表（plotly）
- 统计报告

## 代码规范

- 使用 pandas 进行数据处理
- 使用 scipy.stats 进行统计检验
- 使用 matplotlib + seaborn 绑定学术风格
- 图表保存为 PNG (300 DPI) 和 PDF
