---
name: architecture-diagram
description: "交互式架构图 HTML 生成（系统架构、数据流、组件关系）。"
version: 1.0.0
author: TS2 (adapted from Hermes)
platforms: [linux, macos, windows]
metadata:
  ts2:
    tags: [architecture, diagram, system-design, visualization, html]
    category: creative
---

# 架构图生成技能

生成自包含的 HTML 架构图文件，支持交互式缩放、拖拽和悬停查看详情。

## 使用场景

- 系统架构图
- 数据流图
- 微服务关系图
- 组件依赖图
- 网络拓扑图

## 工作流

1. 分析用户描述的架构
2. 识别组件、连接和数据流
3. 生成 HTML 文件（内嵌 CSS + JS）
4. 使用 `write_file` 保存

## 设计原则

- **层次清晰**：从左到右或从上到下的数据流方向
- **颜色编码**：不同类型的组件使用不同颜色
  - 外部服务：蓝色
  - 核心服务：绿色
  - 数据存储：橙色
  - 消息队列：紫色
  - 网关/代理：灰色
- **连接标注**：箭头上标注协议和数据类型
- **响应式**：支持缩放和拖拽

## 输出格式

单文件 HTML，包含：
- SVG 渲染的架构图
- CSS 动画和交互
- JS 拖拽和缩放支持
- 图例和说明
