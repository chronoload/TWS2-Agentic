# FAIL 判定阈值

> 任一条成立则整个文档判 FAIL，不通过不可放行。

## 结构性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 1 | 缺少 RE:KCTSW 任一节 | CRITICAL |
| 2 | 节顺序错误 | CRITICAL |
| 3 | 标题格式不符（非 `# X：{title}`） | CRITICAL |
| 4 | 开头非 `## 中心问题：{desc}` 格式 | WARNING |

## 内容性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 5 | 非代码内容 < min_chars 阈值 | CRITICAL |
| 6 | 总行数 < min_lines 阈值 | CRITICAL |
| 7 | 无完整的定理→证明→反例闭环（若 require_theorem_proof=true） | CRITICAL |
| 8 | W 节未回到 R 的子问题 | CRITICAL |
| 9 | K 节是纯表格+公式罗列（无展开说明） | CRITICAL |
| 10 | 代码出现在 S 节之前（setup chunk 除外） | CRITICAL |
| 11 | Filler 比例 > max_filler_ratio | WARNING |
| 12 | ≥5 段 CRITICAL filler | CRITICAL |

## 事实性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 13 | 存在虚构定理/虚构引用 | CRITICAL |
| 14 | 公式与标准数学不符 | CRITICAL |
| 15 | 代码存在语法错误或不可用 API | CRITICAL |

## 框架一致性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 16 | framework 的 required_definition 在 K 节缺失 | CRITICAL |
| 17 | framework 的 required_theorem 在 T 节缺失或证明不完整 | CRITICAL |
| 18 | W 节未回答 framework 中列出的 sub_question | CRITICAL |
| 19 | Writer 的 Framework Delta 标注了偏离但理由不成立 | WARNING |

## 编译性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 20 | 任一代码块运行时报错 | CRITICAL |
| 21 | 代码输出与正文数据不一致 | CRITICAL |
| 22 | PDF 编译失败 | CRITICAL |
| 23 | 依赖文件（数据/图片）缺失 | CRITICAL |

## 跨文档一致性 FAIL

| # | 条件 | 严重度 |
|---|------|--------|
| 24 | 某文档引用了尚未引入的概念 | CRITICAL |
| 25 | 同一概念使用不同名称/符号 | CRITICAL |
| 26 | 存在循环依赖 | CRITICAL |
| 27 | 术语冲突（同一术语不同定义） | CRITICAL |
| 28 | 引用指向不存在的文档 | CRITICAL |
