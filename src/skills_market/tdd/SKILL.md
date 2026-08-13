---
name: tdd
version: "1.0"
description: "测试驱动开发 — Red-Green-Refactor 循环，先写测试再写实现"
category: software-development
enabled: true
tags: [testing, tdd, development]
allowed_tools: [read_file, write_file, execute_command, search_code]
---

# 测试驱动开发 (TDD)

严格遵循 Red-Green-Refactor 循环。

## 循环

1. **🔴 Red**: 写一个失败的测试
   - 只写最小测试代码
   - 运行确认测试失败
   - 测试名清晰描述期望行为

2. **🟢 Green**: 写最少的代码让测试通过
   - 不追求完美实现
   - 硬编码也行，只要测试通过
   - 运行确认测试通过

3. **🔵 Refactor**: 重构
   - 消除重复
   - 改善命名
   - 简化逻辑
   - 每次重构后运行测试确认不破坏

## 测试命名

```
test_{方法名}_{场景}_{期望结果}
```

例: `test_divide_by_zero_raises_valueerror`

## 测试结构 (AAA)

```python
def test_feature_scenario():
    # Arrange - 准备
    calc = Calculator()

    # Act - 执行
    result = calc.add(2, 3)

    # Assert - 断言
    assert result == 5
```

## 规则
- 永远不写生产代码，除非是为了让失败测试通过
- 每个循环只写一个测试
- 重构时不添加新功能
- 测试代码和生产代码同等重要
