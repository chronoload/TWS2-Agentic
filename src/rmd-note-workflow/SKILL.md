# RMD Workflow Skill

Rmd 写作工作流插件，支持两种模式。

## 触发条件

当用户请求以下操作时激活：
- "从零搭建 Rmd 项目" / "bootstrap Rmd project"
- "开始写 L{N}-L{M}" / "write lessons L{N}-L{M}"
- "编译 Rmd" / "compile Rmd"
- "检查格式" / "scan Rmd"
- "生成索引" / "generate index"

## 模式 1: Bootstrap（从零搭建）

1. 读取 `core/prompts/bootstrap.md` 获取引导流程
2. 按 Step 0-6 与用户交互
3. 生成 `config.json` + 目录结构 + 模板文件
4. 运行环境插件检测和安装

## 模式 2: Pipeline（生产流水线）

1. 读取 `config.json` 获取项目配置
2. 运行 `scripts/orchestrator.py` 管理流水线
3. 按 Phase 1-4 执行（Architect → Writer → Review → Gate）
4. 使用 `scripts/compiler.py` 编译输出
5. 使用 `scripts/indexer.py` 更新索引

## 关键文件

- `core/prompts/*.md` — 9 个角色提示词
- `core/quality/*.md` — 质量标准和 FAIL 阈值
- `core/templates/*.md` — framework/YAML/dispatch 模板
- `scripts/*.py` — 编排/编译/扫描/索引/依赖/术语脚本
- `plugins/*.py` — 环境管理插件

## 配置

所有配置集中在 `config.json`，分两层：
- `content.*` — 内容配置（插件管理）
- `infra.*` — 基础设施配置（项目本地）
