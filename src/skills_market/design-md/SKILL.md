---
name: design-md
description: "编写/验证/导出 DESIGN.md 设计令牌规范文件。"
version: 1.0.0
author: TS2 (adapted from Hermes)
platforms: [linux, macos, windows]
metadata:
  ts2:
    tags: [design, design-system, tokens, ui, accessibility, tailwind]
    category: creative
---

# DESIGN.md 技能

DESIGN.md 是描述视觉身份的规范文件，一个文件结合：
- **YAML front matter** — 机器可读的设计令牌
- **Markdown body** — 人类可读的设计原理

## 使用场景

- 用户要求创建 DESIGN.md 文件或设计令牌
- 用户希望跨项目保持一致的 UI/品牌
- 用户需要对比度/WCAG 无障碍验证

## 文件结构

```md
---
version: alpha
name: 项目名称
description: 设计风格描述
colors:
  primary: "#1A1C1E"
  secondary: "#6C7278"
  tertiary: "#B8422E"
  neutral: "#F7F5F2"
typography:
  h1:
    fontFamily: Noto Sans SC
    fontSize: 3rem
    fontWeight: 700
    lineHeight: 1.1
rounded:
  sm: 4px
  md: 8px
  lg: 16px
spacing:
  sm: 8px
  md: 16px
  lg: 24px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: 12px
---

## 概述
设计理念说明...

## 颜色
- **Primary (#1A1C1E):** 深墨色用于标题和核心文本

## 排版
字体选择和层级说明...

## 组件
组件使用说明...
```

## 令牌类型

| 类型 | 格式 | 示例 |
|------|------|------|
| 颜色 | `#` + hex | `"#1A1C1E"` |
| 尺寸 | 数字+单位 | `48px`, `1rem` |
| 令牌引用 | `{path.to.token}` | `{colors.primary}` |
| 排版 | 对象 | fontFamily, fontSize, fontWeight, lineHeight |

## 注意事项

- 不要嵌套组件变体，`button-primary-hover` 作为兄弟键
- Hex 颜色必须用引号包裹
- 令牌引用使用点路径：`{colors.primary}`
