---
name: weather
version: "1.0"
description: "天气查询 — 获取当前和预报天气信息"
category: productivity
enabled: true
tags: [weather, utility]
allowed_tools: [web_search]
---

# 天气查询

查询天气信息，支持当前天气和预报。

## 使用方式

通过 `web_search` 工具搜索天气信息：
- 查询格式: `{城市} 天气`
- 可指定未来天数

## 输出格式

```markdown
## [城市] 天气

**当前**: 🌤 晴, 25°C, 湿度 45%, 风速 3m/s

**未来3天**:
| 日期 | 天气 | 高温 | 低温 |
|------|------|------|------|
| 明天 | ☁ 多云 | 23°C | 18°C |
| 后天 | 🌧 小雨 | 20°C | 16°C |
| 大后天 | 🌤 晴 | 26°C | 19°C |
```
