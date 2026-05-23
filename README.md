# TS2 - 课程教学管理系统 / AI Research Assistant

一个功能强大的课程跟踪和进度管理系统，集成了 MCP (Model Context Protocol) 驱动的 AI 助手，支持可视化进度追踪、资源管理、数学公式渲染和本地知识库检索增强生成。

## 项目简介
###演示视频
TS2-Agentic_(https://www.bilibili.com/video/BV1c7Gq66Ex7/?vd_source=263a088cf13d67fa3a899dd3bd107d0a)
TS2-OpenSource 是一个集课程管理、学习追踪和 AI 辅助于一体的综合平台：

- **课程管理**：结构化课程组织，顺序记录学习进度
- **智能助手**：基于 MCP 协议的 AI 助手，支持多 LLM 提供商
- **知识检索**：RAG 系统支持本地文档索引和语义搜索
- **进度可视化**：直观的 GUI 进度追踪，完成消除+弹出下一步
- **资源管理**：PDF/URL/Video/Image 资源索引和预览
- **公式渲染**：LaTeX 转 UTF-8 数学公式显示
- **工作流引擎**：自动化任务执行和预定义工作流

## 核心功能

- **课程管理**: 顺序记录学习进度，支持新建/编辑课程
- **进度可视化**: GUI 可视化进度追踪，完成消除+弹出下一步
- **MCP Agent**: Model Context Protocol 驱动的AI助手
- **数学公式**: LaTeX 到 UTF-8 转换，支持希腊字母和数学符号
- **资源管理**: PDF/URL/Video/Image 资源索引
- **多格式支持**: JSON / 单MD / 批量MD 导入
- **RAG系统**: 检索增强生成，支持本地知识库
- **工作流引擎**: 自动化任务执行

## 完整依赖架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        主入口层                                  │
├─────────────────────────────────────────────────────────────────┤
│  run.py (启动脚本)                                               │
│    └── course_tracker.py (课程管理 + GUI + 进度可视化)            │
│            ├── md_builder.py (Markdown解析 + 目录解析)            │
│            │       ├── data_converter.py (数据转换)               │
│            │       └── tex_to_utf8.py (LaTeX→UTF8)              │
│            │                                                   │
│            └── mcp/ (AI Agent系统)                              │
│                    ├── agent.py (Agent核心逻辑)                  │
│                    │       ├── llm.py (LLM接口 + 多提供商)       │
│                    │       │       ├── tools.py (工具定义)       │
│                    │       │       └── ws2_tools.py (WS2工具)   │
│                    │       │                                     │
│                    │       ├── ws2_synergy.py (协同功能)         │
│                    │       ├── ws2_synergy_ui.py (协同UI)        │
│                    │       └── ws2_research.py (研究工具)        │
│                    │       │                                     │
│                    │       ├── agent_assistant.py (Agent UI)     │
│                    │       ├── ui.py (通用UI组件)                │
│                    │       ├── config.py (配置管理)              │
│                    │       ├── config_ui.py (配置界面)           │
│                    │       ├── context_compactor.py (上下文压缩)  │
│                    │       ├── event_logger.py (事件日志)         │
│                    │       ├── git_searcher.py (Git搜索)         │
│                    │       ├── skills.py (技能系统)              │
│                    │       ├── predefined_workflows.py (预定义工作流)│
│                    │       └── workflow_engine.py (工作流引擎)    │
│                    │                                             │
│                    ├── rag/ (检索增强生成)                       │
│                    │       ├── auto_rag.py (自动RAG)             │
│                    │       ├── retriever.py (检索器)             │
│                    │       ├── vector_store.py (向量存储)        │
│                    │       ├── rag_engine.py (RAG引擎)          │
│                    │       ├── knowledge_graph.py (知识图谱)      │
│                    │       ├── document_loader.py (文档加载)     │
│                    │       └── text_splitter.py (文本分割)       │
│                    │                                             │
│                    ├── prompt/ (提示词系统)                      │
│                    │       ├── builder.py (提示词构建)           │
│                    │       ├── context_window.py (上下文窗口)    │
│                    │       ├── templates.py (模板)               │
│                    │       ├── variants.py (变体)               │
│                    │       ├── components.py (组件)             │
│                    │       └── workspace.py (工作区)            │
│                    │                                             │
│                    └── cache/ (缓存系统)                        │
│                            ├── lru_cache.py (LRU缓存)           │
│                            ├── disk.py (磁盘缓存)               │
│                            ├── model_cache.py (模型缓存)        │
│                            ├── state_manager.py (状态管理)      │
│                            ├── context_reloader.py (上下文重载) │
│                            └── ui_state.py (UI状态)             │
│                                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 系统依赖

**Linux (Ubuntu/Debian):**
```bash
sudo apt install poppler-utils  # PDF转图片
```

**macOS:**
```bash
brew install poppler  # PDF转图片
```

### 依赖说明

| 分类 | 包 | 用途 |
|------|-----|------|
| **核心** | numpy, matplotlib, tkinter | 数据处理、可视化、GUI |
| **MCP系统** | openai, anthropic, aiohttp | LLM支持、异步HTTP |
| **RAG** | chromadb, faiss-cpu | 向量数据库、嵌入模型 |
| **PDF处理** | PyPDF2, pdf2image | PDF读取、PDF转图片 |
| **工具** | pyyaml, requests, beautifulsoup4, feedparser | 数据格式、网络、解析 |

### 2. 创建快捷方式

双击运行 `create_shortcuts.py` 或命令行:
```bash
python create_shortcuts.py
```

### 3. 运行

方式一：使用快捷方式
- 双击 `TS2-课程追踪系统.lnk`

方式二：命令行运行
```bash
python run.py
```

方式三：直接运行源码
```bash
cd src
python course_tracker.py
```

## 项目结构

```
TS2-OpenSource/
├── src/                              # 源代码
│   ├── course_tracker.py             # 主入口 - 课程管理系统
│   ├── md_builder.py                # Markdown解析器
│   ├── tex_to_utf8.py              # LaTeX转UTF-8
│   ├── data_converter.py            # 数据转换
│   ├── ws2_synergy.py              # WS2协同功能
│   ├── ws2_synergy_ui.py           # WS2协同UI
│   ├── ws2_research.py             # 研究工具
│   │
│   └── mcp/                         # MCP Agent系统
│       ├── agent.py                 # Agent核心
│       ├── agent_assistant.py       # Agent UI界面
│       ├── llm.py                   # LLM接口
│       ├── tools.py                 # 工具定义
│       ├── ws2_tools.py             # WS2工具集
│       ├── ui.py                    # UI组件
│       ├── config.py                # 配置管理
│       ├── config_ui.py             # 配置界面
│       ├── context_compactor.py      # 上下文压缩
│       ├── event_logger.py          # 事件日志
│       ├── git_searcher.py          # Git搜索
│       ├── skills.py                # 技能系统
│       ├── predefined_workflows.py  # 预定义工作流
│       ├── workflow_engine.py       # 工作流引擎
│       │
│       ├── rag/                     # RAG系统
│       │   ├── auto_rag.py
│       │   ├── retriever.py
│       │   ├── vector_store.py
│       │   ├── rag_engine.py
│       │   ├── knowledge_graph.py
│       │   ├── document_loader.py
│       │   └── text_splitter.py
│       │
│       ├── prompt/                  # 提示词系统
│       │   ├── builder.py
│       │   ├── context_window.py
│       │   ├── templates.py
│       │   ├── variants.py
│       │   ├── components.py
│       │   └── workspace.py
│       │
│       └── cache/                   # 缓存系统
│           ├── lru_cache.py
│           ├── disk.py
│           ├── model_cache.py
│           ├── state_manager.py
│           ├── context_reloader.py
│           └── ui_state.py
│
├── tests/                           # 测试文件
├── config/                          # 配置文件
├── examples/                        # 示例数据
│   └── courses_structured.json     # 课程数据结构
├── docs/                            # 文档
│
├── run.py                           # 启动脚本
├── create_shortcuts.py              # 快捷方式创建
├── README.md                        # 本文档
├── requirements.txt                 # 依赖清单
├── LICENSE                          # MIT许可证
└── .gitignore                       # Git忽略规则
```

## 核心模块说明

### course_tracker.py (主入口)
- 课程进度GUI可视化
- 资源管理（PDF/URL/Video）
- 导入/导出功能
- 进度统计图表

### md_builder.py
- Markdown文件解析
- 批量目录解析
- 课程结构生成
- Rmd文件支持

### tex_to_utf8.py
- LaTeX数学公式转UTF-8
- 希腊字母: α, β, γ, δ, π, ω...
- 数学符号: ∫, ∑, √, ∞, ∂, ∇...
- 分数、根号、上下标

### ws2_synergy.py / ws2_synergy_ui.py
- WS2协同功能
- 研究工作流
- 多工具协作

### ws2_research.py
- 研究分析工具
- 文献搜索
- 知识管理

### mcp/agent.py (Agent核心)
- 多轮对话管理
- 工具调用
- 上下文维护
- 错误恢复

### mcp/agent_assistant.py (Agent UI)
- 图形界面
- 流式输出
- 调试面板
- 性能监控

### mcp/llm.py (LLM接口)
- OpenAI支持
- Anthropic支持
- 多提供商管理
- 流式响应
- 工具调用协议

### mcp/rag/ (RAG系统)
- 文档向量化
- 语义检索
- 知识图谱构建
- 自动索引

### mcp/prompt/ (提示词系统)
- 动态提示词构建
- 上下文窗口管理
- 模板系统
- 工作区管理

### mcp/cache/ (缓存系统)
- LRU缓存
- 磁盘持久化
- 模型缓存
- 状态管理

## 数据格式

课程数据使用JSON格式:
```json
{
  "courses": [{
    "course_title": "课程名称",
    "domain": "领域",
    "total_hours": 40,
    "lessons": [{
      "lesson_title": "课时标题",
      "sections": [{
        "section_title": "章节标题",
        "completed": false,
        "resources": []
      }]
    }]
  }]
}
```

## 运行环境

- Python 3.10+
- tkinter (GUI) - Python内置
- matplotlib (图表) - pip install matplotlib
- numpy (数据处理) - pip install numpy
- 其他依赖见 requirements.txt

## 快捷方式

运行 `create_shortcuts.py` 创建以下快捷方式：

### 程序快捷方式
- TS2-课程追踪系统
- TS2-课程追踪(源码)
- TS2-MD构建器
- TS2-公式转换器
- TS2-MCP-Agent

### 目录快捷方式
- TS2-src
- TS2-mcp
- TS2-tests
- TS2-config
- TS2-examples
- TS2-docs

### 命令行快捷方式
- 终端-TS2

## 许可证

MIT License

## 作者

Pinechan

