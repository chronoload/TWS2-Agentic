---
name: nano-pdf
version: "1.0"
description: "PDF 文档处理 — 读取、提取文本、分析结构"
category: productivity
enabled: true
tags: [pdf, document, extraction]
allowed_tools: [pdf_reader, read_file, write_file]
---

# PDF 文档处理

处理PDF文档，提取和分析内容。

## 能力

1. **文本提取**: 从PDF提取纯文本
2. **结构分析**: 识别标题、段落、表格
3. **元数据读取**: 作者、日期、页数
4. **批量处理**: 处理多个PDF文件

## 使用方式

使用 `pdf_reader` 工具读取PDF文件：
- 传入文件路径
- 可指定页码范围
- 返回结构化文本

## 输出格式

```markdown
# [PDF标题]

**元数据**:
- 作者: ...
- 页数: ...
- 创建日期: ...

## 第1页
[提取的文本内容]

## 第2页
[提取的文本内容]
```

## 注意事项
- 扫描版PDF需要OCR支持
- 表格提取可能不完美
- 公式以文本形式提取
