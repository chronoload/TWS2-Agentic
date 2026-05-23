# TS2 OpenSource - 快速使用指南

## 🚀 快速启动

### 方法1: 使用快捷方式（推荐）

1. 双击运行 `create_shortcuts.py`
2. 在项目目录中会出现多个 `.lnk` 快捷方式文件
3. 双击对应的快捷方式即可启动

### 方法2: 命令行启动

```bash
# 主程序 - 课程追踪系统
python run.py

# MCP Agent AI助手
python run_mcp_agent.py

# 直接运行源码
cd src
python course_tracker.py
```

## 📦 模块说明

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 主入口 | course_tracker.py | 课程管理系统 + GUI |
| Markdown解析 | md_builder.py | 解析课程MD文件 |
| 公式转换 | tex_to_utf8.py | LaTeX→UTF-8 |
| 数据转换 | data_converter.py | JSON/CSV/XLSX转换 |

### MCP Agent系统

| 模块 | 功能 |
|------|------|
| agent.py | Agent核心逻辑 |
| llm.py | LLM接口（支持多提供商）|
| tools.py | 工具定义 |
| ws2_tools.py | WS2工具集（38个工具）|
| agent_assistant.py | Agent UI界面 |
| rag/ | 检索增强生成系统 |
| prompt/ | 提示词管理系统 |
| cache/ | 缓存系统 |

## 🔧 测试工具

```bash
# 测试所有模块导入
python test_imports.py

# 测试MCP Agent系统
python test_mcp.py
```

## ⚙️ 配置

1. 复制配置模板:
   ```bash
   cp config/project.json config/config.json
   ```

2. 编辑配置文件，添加API密钥

3. MCP Agent需要配置LLM提供商的API密钥

## 📁 项目结构

```
TS2-OpenSource/
├── src/                          # 源代码
│   ├── course_tracker.py         # 主入口
│   ├── md_builder.py            # Markdown解析
│   ├── tex_to_utf8.py          # 公式转换
│   ├── data_converter.py        # 数据转换
│   ├── ws2_*.py               # WS2功能
│   └── mcp/                    # MCP Agent系统
│       ├── agent.py            # Agent核心
│       ├── llm.py              # LLM接口
│       ├── tools.py            # 工具
│       ├── rag/                # RAG系统
│       ├── prompt/             # 提示词
│       └── cache/              # 缓存
│
├── tests/                       # 测试文件
├── config/                      # 配置
├── examples/                    # 示例
│
├── run.py                       # 启动脚本
├── run_mcp_agent.py            # MCP启动
├── test_imports.py             # 导入测试
├── test_mcp.py                 # MCP测试
├── create_shortcuts.py         # 快捷方式
└── README.md                   # 文档
```

## 🛠️ 常用操作

### 启动MCP Agent

```bash
# 方式1: 使用启动脚本
python run_mcp_agent.py

# 方式2: 直接运行
python src/mcp/agent_assistant.py
```

### 测试MCP

```bash
# 测试所有导入
python test_imports.py

# 测试MCP完整功能
python test_mcp.py
```

### 创建快捷方式

```bash
python create_shortcuts.py
```

## ⚠️ 注意事项

1. MCP Agent需要配置API密钥才能连接LLM
2. 首次运行会自动创建必要的配置文件
3. 所有模块导入测试必须通过才能正常使用

## 📚 更多信息

详见 [README.md](README.md)
