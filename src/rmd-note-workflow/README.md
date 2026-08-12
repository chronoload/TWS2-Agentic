# RMD Workflow Plugin

平台无关的 Rmd 写作工作流插件。

## 功能

- **Bootstrap**: 交互式引导从零搭建 Rmd 项目
- **Pipeline**: 多角色并发流水线（Architect → Writer → Review → Compile）
- **质量控制**: RE:KCTSW 叙事哲学 + 结构化 FAIL 阈值
- **编译引擎**: 并发编译 + 失败重试 + 格式预扫描
- **环境管理**: R/Python/LaTeX 依赖检测和锁定

## 快速开始

### Bootstrap（从零搭建）

```bash
python scripts/orchestrator.py bootstrap
```

按提示回答项目问题，自动生成 config.json 和目录结构。

### Pipeline（生产流水线）

```bash
# 1. 运行 Architect
python scripts/orchestrator.py architect --lessons L01-L21

# 2. 运行 Writer（并发）
python scripts/orchestrator.py write --batch B0

# 3. 运行 Review（5 角色并发）
python scripts/orchestrator.py review --batch B0

# 4. 编译
python scripts/compiler.py --dir Notes/课程大纲 --format pdf
```

## 目录结构

```
rmd-workflow/
├── core/           # 提示词 + 质量标准 + 模板
├── scripts/        # 编排 + 编译 + 扫描
├── plugins/        # 环境管理（可扩展）
└── adapters/       # 平台适配（OpenCode/Claude）
```

## 配置

详见 `config.json` schema（design doc）。

## 扩展

添加新环境插件：在 `plugins/` 下创建新 .py 文件，实现 `EnvPlugin` 接口。
