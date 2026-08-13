---
name: systematic-debugging
version: "1.0"
description: "系统调试 — 科学方法驱动的bug定位和修复流程"
category: software-development
enabled: true
tags: [debugging, troubleshooting, development]
allowed_tools: [read_file, search_code, execute_command, list_directory]
---

# 系统调试

用科学方法调试，而非随机尝试。

## 流程

### 1. 复现
- 找到最小可复现步骤
- 记录环境（OS/版本/配置）
- 确认复现率（100%? 间歇性?）

### 2. 观察
- 收集错误信息（traceback/log/返回值）
- 检查最近变更（git diff/git log）
- 查看相关代码路径

### 3. 假设
- 基于观察提出最可能的假设
- 按可能性排序
- 每个假设必须是可验证的

### 4. 实验
- 设计最小实验验证假设
- 一次只改一个变量
- 记录实验结果

### 5. 修复
- 针对确认的根因修复
- 添加回归测试
- 验证修复不引入新问题

## 调试技巧

| 技术 | 适用场景 |
|------|----------|
| 二分法 | 定位引入bug的commit |
| 日志注入 | 追踪数据流 |
| 断点调试 | 复杂状态问题 |
| 最小用例 | 隔离问题范围 |
| 橡皮鸭 | 理清思路 |

## 规则
- 不猜测，先观察
- 一次只验证一个假设
- 修复后必须写回归测试
- 记录调试过程供未来参考
