---
name: skill-creator
version: "1.0"
description: "Skill 创建工具 — 帮助创建新的 TS2 Skills"
category: software-development
enabled: true
tags: [skill, creation, meta]
allowed_tools: [read_file, write_file, list_directory]
---

# Skill 创建工具

帮助创建新的 TS2 Skills。

## 创建流程

1. **确定Skill目标**: 一句话描述这个Skill做什么
2. **选择分类**: software-development / research / productivity / creative
3. **编写SKILL.md**: 使用以下模板

## SKILL.md 模板

```markdown
---
name: [skill-name]
version: "1.0"
description: "[一句话描述]"
category: [category]
enabled: true
tags: [tag1, tag2]
allowed_tools: [tool1, tool2]
---

# [Skill 名称]

[详细描述]

## 工作流程

1. 步骤一
2. 步骤二
3. 步骤三

## 输出格式

[期望的输出格式]

## 规则

- 规则一
- 规则二
```

## 命名规范
- 目录名: kebab-case (如 `my-skill`)
- name字段: 同目录名
- 一个Skill一个目录
- 必须包含 SKILL.md
