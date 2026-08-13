---
name: arxiv-research
version: "1.0"
description: "ArXiv 学术论文搜索和分析 — 搜索、摘要、对比、趋势追踪"
category: research
enabled: true
tags: [arxiv, research, papers, academic]
allowed_tools: [web_search, arxiv_search]
---

# ArXiv 学术研究

搜索和分析 ArXiv 论文，支持物理科学领域。

## 工作流

1. **搜索**: 使用 `arxiv_search` 工具搜索相关论文
2. **筛选**: 按相关性、引用、时间排序
3. **摘要**: 提取核心贡献、方法、结果
4. **对比**: 比较多篇论文的方法差异
5. **趋势**: 识别研究趋势和空白

## 搜索策略

- 精确搜索: 用引号包裹短语 `"quantum entanglement"`
- 分类过滤: `cat:quant-ph` 或 `cat:hep-th`
- 时间范围: 优先近2年，兼顾经典论文
- 作者追踪: `au:Witten`

## 论文分析模板

```markdown
## [论文标题]
- **作者**: ...
- **日期**: ...
- **arXiv ID**: ...
- **核心贡献**: 一句话
- **方法**: 关键技术
- **结果**: 主要发现
- **局限**: 已知限制
- **与我的研究关联**: ...
```

## 物理科学常用分类
- `astro-ph` 天体物理
- `cond-mat` 凝聚态
- `gr-qc` 广义相对论
- `hep-ex/hep-lat/hep-ph/hep-th` 高能物理
- `math-ph` 数学物理
- `quant-ph` 量子物理
