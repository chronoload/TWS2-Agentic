---
name: summarize
version: "1.0"
description: "文本摘要 — 提取关键信息、生成结构化摘要"
category: productivity
enabled: true
tags: [summarize, extraction, notes]
allowed_tools: [read_file, summarize_tool]
---

# 文本摘要

从长文本中提取关键信息，生成结构化摘要。

## 摘要模式

### 简要摘要
3-5句话概括核心内容。

### 结构化摘要
```markdown
## 摘要
[一段话概述]

## 关键要点
1. ...
2. ...
3. ...

## 核心数据
- ...

## 待跟进
- ...
```

### 学术摘要
按 IMRAD 结构：
- **背景**: 为什么研究
- **方法**: 怎么研究
- **结果**: 发现什么
- **结论**: 意味着什么

## 规则
- 不添加原文没有的信息
- 保留关键数据和数字
- 标注不确定内容
- 区分事实和观点
