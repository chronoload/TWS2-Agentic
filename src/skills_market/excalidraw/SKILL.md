---
name: excalidraw
description: "手绘风格 Excalidraw JSON 图表（架构图、流程图、序列图）。"
version: 1.0.0
author: TS2 (adapted from Hermes)
platforms: [linux, macos, windows]
metadata:
  ts2:
    tags: [Excalidraw, Diagrams, Flowcharts, Architecture, Visualization, JSON]
    category: creative
---

# Excalidraw 图表技能

通过编写标准 Excalidraw 元素 JSON 并保存为 `.excalidraw` 文件来创建图表。文件可拖放到 [excalidraw.com](https://excalidraw.com) 查看和编辑。

## 使用场景

生成 `.excalidraw` 文件用于：架构图、流程图、序列图、概念图等。

## 工作流

1. 编写元素 JSON — Excalidraw 元素对象数组
2. 使用 `write_file` 保存为 `.excalidraw` 文件
3. 在 excalidraw.com 打开查看

### 保存图表

将元素数组包装在标准 `.excalidraw` 信封中：

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "ts2-agent",
  "elements": [ ...元素数组... ],
  "appState": {
    "viewBackgroundColor": "#ffffff"
  }
}
```

## 元素格式参考

### 必填字段（所有元素）
`type`, `id`（唯一字符串）, `x`, `y`, `width`, `height`

### 默认值（可省略）
- `strokeColor`: `"#1e1e1e"`
- `backgroundColor`: `"transparent"`
- `fillStyle`: `"solid"`
- `strokeWidth`: `2`
- `roughness`: `1`（手绘效果）
- `opacity`: `100`

### 元素类型

**矩形**:
```json
{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 100 }
```

**椭圆**:
```json
{ "type": "ellipse", "id": "e1", "x": 400, "y": 100, "width": 150, "height": 100 }
```

**菱形**:
```json
{ "type": "diamond", "id": "d1", "x": 650, "y": 100, "width": 150, "height": 100 }
```

**文本**:
```json
{ "type": "text", "id": "t1", "x": 120, "y": 130, "width": 80, "height": 25, "text": "Hello", "fontSize": 20, "fontFamily": 1 }
```

**箭头**:
```json
{ "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 100, "height": 0, "points": [[0,0],[100,0]], "startBinding": "r1", "endBinding": "e1" }
```

**线条**:
```json
{ "type": "line", "id": "l1", "x": 100, "y": 300, "width": 200, "height": 0, "points": [[0,0],[200,0]] }
```

## 布局技巧

- 矩形间距：水平 300px，垂直 150px
- 文本居中：x + width/2 - textWidth/2, y + height/2 - textHeight/2
- 箭头连接：使用 `startBinding` 和 `endBinding` 引用元素 id
- 分组：使用 `"groupIds": ["group1"]`

## 颜色方案

- 主色：`#1e1e1e`（深灰）
- 强调色：`#e03131`（红）、`#1971c2`（蓝）、`#2f9e44`（绿）
- 背景色：`#ffffff`（白）、`#f8f9fa`（浅灰）
