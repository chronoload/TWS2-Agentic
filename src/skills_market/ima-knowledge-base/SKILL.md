---
name: ima-knowledge-base
description: This skill should be used when accessing and managing the IMA knowledge base, including searching for files, downloading resources, and organizing local storage.
---

# 腾讯IMA知识库接入指南

本技能提供访问腾讯IMA个人知识库的工作流程，包括搜索文件、下载资源到本地存储等。

## 腾讯IMA知识库接入方式

腾讯IMA知识库提供三种接入方案，按复杂度递增：

### 1. 零代码方案（适合公众号运营）

**适用场景**：个人/企业公众号运营，想零开发拥有AI问答客服

**接入步骤**：
1. 电脑端安装ima copilot (ima.qq.com) → 微信扫码登录
2. 左侧「个人知识库」→ 批量上传PDF/Word/图片或右键新建文件夹
3. 右上角「分享」→ 复制小程序路径（形如：`pages/index/index?k=xxx`）
4. 登录微信公众平台 → 自定义菜单 → 新增子菜单
5. 动作选「跳转小程序」→ 搜索「ima 知识库」→ 粘贴小程序路径
6. 保存并发布，粉丝点菜单即可向知识库提问

**特点**：
- 无需编程
- 资料更新后点「重新索引」，前端无需重新发布
- 同一知识库可绑定多个公众号/小程序
- 支持权限分级（只读/可写）

### 2. 低代码方案（适合网页/小程序嵌入）

**适用场景**：需要网页/小程序/微信群嵌入，且想定期自动同步公众号文章

**平台地址**：https://yuanqi.tencent.com（腾讯元器）

**接入步骤**：
1. 登录腾讯元器 → 左侧「知识库」→ 新建知识库
2. 支持3种数据源：
   - 「公众号文章」- 扫码授权自动同步
   - 「本地文件」- 上传doc/docx/txt/PDF
   - 「网页链接」- 输入URL自动抓取
3. 创建智能体 → 绑定知识库
4. 发布智能体 → 点击「更多」→「调用API」
5. 获取调用信息：
   - `url`：API调用地址
   - `assistant_id`：智能体ID
   - `token`：认证令牌

**API调用示例**：
```python
import requests

url = "https://yuanqi.tencent.com/api/v1/chat"
headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
}
data = {
    "assistant_id": "your_assistant_id",
    "user_id": "username",
    "messages": [
        {"role": "user", "content": "你的问题"}
    ]
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

**特点**：
- 支持流式和非流式响应
- 支持混元大模型和DeepSeek-R1
- 支持插件（网页解析、混元生图、图片理解）
- 工作流式低代码编辑

### 3. 专业方案（适合企业级定制）

**适用场景**：需要完全控制、定制化部署、企业级知识管理

**开源框架**：WeKnora（维娜拉）

**GitHub地址**：https://github.com/Tencent/WeKnora

**核心特性**：
- 基于RAG（检索增强生成）架构
- 支持多格式文档解析：PDF/Word/Txt/Markdown/图片（OCR）
- 支持多种检索策略：关键词/向量/知识图谱
- 暴露标准REST/JSON API
- 可本地部署，支持Docker

**安装部署**：
```bash
# 克隆项目
git clone https://github.com/Tencent/WeKnora.git
cd WeKnora

# 复制配置文件
cp .env.example .env

# 编辑配置，设置Ollama地址等
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# 使用Docker运行
docker-compose up -d
```

**REST API示例**：
```bash
# 文档检索
curl -X POST http://localhost:8000/v1/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你的问题",
    "topk": 5
  }'

# 问答生成
curl -X POST http://localhost:8000/v1/qa \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你的问题",
    "use_rag": true
  }'
```

**特点**：
- 完全开源，可自由定制
- 支持本地部署，数据安全
- 模块化设计，全流程解耦
- 支持接入本地Ollama模型

## 本技能定位

本技能主要针对**低代码方案（腾讯元器）**，提供以下功能：
- 通过API搜索知识库中的文件和内容
- 下载知识库中的文档到本地
- 同步知识库内容到本地存储
- 集成本地项目与知识库资源

## Prerequisites and Environment

### Required Dependencies

```bash
pip install requests
```

### Configuration - 腾讯元器API

#### 获取API凭证

1. 登录腾讯元器：https://yuanqi.tencent.com
2. 创建智能体并绑定知识库
3. 发布智能体 → 点击「更多」→「调用API」
4. 复制以下信息：
   - `url`：API调用地址
   - `assistant_id`：智能体ID
   - `token`：认证令牌

#### 配置文件设置

编辑 `config.py`：
```python
# 腾讯元器API配置
YUANQI_BASE_URL = "https://yuanqi.tencent.com/api/v1"  # API基础地址
YUANQI_ASSISTANT_ID = "your_assistant_id_here"          # 智能体ID
YUANQI_TOKEN = "your_token_here"                        # 认证令牌
YUANQI_USER_ID = "default_user"                         # 用户ID（可选）

# 本地存储配置
LOCAL_STORAGE_DIR = r"C:\Users\qu\WorkBuddy\Claw\knowledge_base_downloads"

# API请求配置
REQUEST_TIMEOUT = 30  # 请求超时时间（秒）
MAX_RETRIES = 3      # 最大重试次数
```

### Directory Structure

```
Claw/
├── knowledge_base_downloads/     # Local storage for downloaded files
├── .codebuddy/skills/ima-knowledge-base/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── search_ima.py
│   │   ├── download_ima.py
│   │   └── sync_ima.py
│   └── references/
│       ├── ima-guide.md
│       └── quick-start.md
```

## Workflow Overview

### 1. 知识库问答工作流

通过腾讯元器API向知识库提问：

```bash
# 向知识库提问（非流式）
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py --query "机器学习基础概念"

# 保存问答结果到文件
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py --query "Python编程技巧" --output "qa_result.json"

# 多个问题批量查询
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py --query-file "questions.txt"
```

### 2. 文档提取工作流

从知识库中提取并保存相关文档：

```bash
# 提取文档内容
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py --query "项目文档" --save-docs

# 提取并分类保存
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py --query "API参考" --save-docs --organize

# 从聊天记录中提取关键文档
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py --chat-id "chat_id_here" --extract-docs
```

### 3. 知识库同步工作流

同步知识库内容到本地存储：

```bash
# 全量同步（基于关键词）
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py --query "所有技术文档"

# 增量同步（仅新增内容）
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py --query "月度报告" --incremental

# 定期同步（带时间戳）
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py --query "每日更新" --timestamp-file "last_sync.txt"
```

## Common Use Cases

### 用例1：智能问答助手

构建基于知识库的问答系统：

```bash
# 创建问答对话
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py --query "深度学习的基本原理是什么？"

# 保存问答历史
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py \
  --query "如何使用Docker容器化Python应用？" \
  --save-history "qa_history.json"

# 批量问答（从文件读取问题）
echo -e "什么是RESTful API？\n如何设计数据库架构？" > questions.txt
python .codebuddy/skills/ima-knowledge-base/scripts/search_ima.py --query-file "questions.txt"
```

### 用例2：知识库内容提取

从知识库中提取特定主题的内容并保存：

```bash
# 提取技术文档内容
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py \
  --query "请列出所有关于微服务架构的文档内容" \
  --save-docs \
  --output "microservices_docs/"

# 提取并分类保存
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py \
  --query "总结所有关于机器学习的知识点" \
  --save-docs \
  --organize-by-topic

# 提取带引用的内容
python .codebuddy/skills/ima-knowledge-base/scripts/download_ima.py \
  --query "Vue.js最佳实践，并引用相关文档" \
  --save-docs \
  --include-references
```

### 用例3：知识库定期同步

定期同步知识库更新到本地：

```bash
# 每日增量同步
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py \
  --query "昨天新增的文档" \
  --incremental \
  --timestamp-file "daily_sync_state.txt"

# 按类别同步
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py \
  --query "产品需求文档" \
  --organize-by-category \
  --output "product_docs/"

# 全量备份
python .codebuddy/skills/ima-knowledge-base/scripts/sync_ima.py \
  --query "所有知识库内容" \
  --full-backup \
  --output "knowledge_base_backup/"
```

## Configuration Options

### 问答参数

- `--query`: 向知识库提问的问题
- `--query-file`: 从文件批量读取问题（每行一个问题）
- `--output`: 保存问答结果到文件
- `--save-history`: 保存问答历史记录
- `--stream`: 是否使用流式响应（默认非流式）

### 文档提取参数

- `--query`: 用于提取文档的提示词
- `--chat-id`: 指定要提取的聊天会话ID
- `--save-docs`: 保存提取的文档内容
- `--organize`: 按主题组织提取的文档
- `--organize-by-topic`: 按主题分类
- `--include-references`: 包含文档引用
- `--output`: 输出目录

### 同步参数

- `--query`: 同步内容的查询条件
- `--incremental`: 仅增量同步（新增内容）
- `--timestamp-file`: 记录同步时间戳的文件
- `--full-backup`: 全量备份模式
- `--organize-by-category`: 按类别组织
- `--output`: 输出目录

### API参数

- `--url`: 自定义API基础地址（覆盖config.py）
- `--assistant-id`: 自定义智能体ID（覆盖config.py）
- `--token`: 自定义令牌（覆盖config.py）
- `--user-id`: 自定义用户ID
- `--timeout`: 请求超时时间（秒）
- `--max-retries`: 最大重试次数

## Local Storage Organization

Files are organized in `knowledge_base_downloads/`:

```
knowledge_base_downloads/
├── by_query/              # Organized by search query
│   ├── deep learning/
│   │   ├── paper1.pdf
│   │   └── paper2.pdf
│   └── project docs/
├── by_type/               # Organized by file type
│   ├── pdf/
│   ├── doc/
│   └── md/
├── by_date/               # Organized by download date
│   ├── 2026-03-15/
│   └── 2026-03-16/
└── metadata.json          # Download metadata
```

## Error Handling

### 认证错误（401 Unauthorized）

**问题**：API令牌无效或已过期

**解决方案**：
1. 检查 `config.py` 中的 `YUANQI_TOKEN` 是否正确
2. 登录腾讯元器重新获取token（智能体→更多→调用API）
3. 确认token未过期（通常长期有效）
4. 检查 `assistant_id` 是否匹配已发布的智能体

### 智能体不存在（404 Not Found）

**问题**：智能体ID不存在或未发布

**解决方案**：
1. 确认智能体已发布（未发布的智能体无法通过API访问）
2. 检查 `assistant_id` 是否复制正确
3. 在腾讯元器平台确认智能体状态
4. 重新发布智能体后再尝试

### 配额超限（429 Rate Limit）

**问题**：API调用次数超限

**解决方案**：
1. 检查腾讯元器的模型额度管理
2. 腾讯赠送1亿token额度，足够数百万次对话
3. 考虑升级到付费套餐
4. 优化查询，减少不必要的调用

### 网络连接错误

**问题**：连接失败或超时

**解决方案**：
1. 检查网络连接是否正常
2. 验证 `YUANQI_BASE_URL` 在 `config.py` 中配置正确
3. 使用 `--timeout` 参数增加超时时间
4. 检查防火墙设置，确保可访问腾讯元器域名

### 响应格式错误

**问题**：API返回的数据格式不符合预期

**解决方案**：
1. 检查API版本是否正确（v1）
2. 查看原始响应内容：添加 `--verbose` 参数
3. 确认请求格式符合API文档要求
4. 检查响应中的错误字段

### 存储问题

**问题**：磁盘空间不足或权限被拒绝

**解决方案**：
1. 检查磁盘空间：`python -c "import shutil; print(shutil.disk_usage('.').free / (1024**3))"` GB
2. 验证输出目录的写权限
3. 使用 `--output` 参数指定其他位置
4. 以管理员身份运行（Windows）或使用sudo（Linux/Mac）

## Performance Tips

1. **Batch Downloads**: Download multiple files at once using `--file-ids`
2. **Incremental Sync**: Use `--incremental` to avoid re-downloading existing files
3. **Parallel Downloads**: Scripts automatically use parallel downloads (5 concurrent)
4. **Cache Search Results**: Search results are cached locally for 1 hour
5. **Limit Results**: Use `--limit` to avoid overwhelming results

## Security Considerations

- **API Key**: Store API key securely in `config.py` (add to .gitignore)
- **HTTPS**: Ensure knowledge base URL uses HTTPS
- **File Validation**: Scripts validate file integrity after download
- **Access Control**: Ensure only authorized users have access to `config.py`

## Troubleshooting

| 问题 | 可能原因 | 解决方案 |
|------|---------|----------|
| 401 Unauthorized | Token无效或过期 | 重新从腾讯元器获取token，检查config.py配置 |
| 404 Not Found | 智能体未发布或ID错误 | 确认智能体已发布，检查assistant_id是否正确 |
| 429 Rate Limit | 调用频率超限 | 查看模型额度，优化查询，考虑升级套餐 |
| Connection timeout | 网络问题或服务器响应慢 | 增加--timeout参数，检查网络连接 |
| JSON decode error | 响应格式错误 | 添加--verbose查看原始响应，检查API版本 |
| Permission denied | 输出目录无写权限 | 检查目录权限，使用--output指定其他位置 |
| Knowledge base not found | 知识库未绑定到智能体 | 在腾讯元器平台确认知识库已绑定 |

## Integration with Other Skills

This skill integrates well with:
- **pdf-toc-processor**: Process downloaded PDF documents
- **file-organizer**: Organize downloaded files
- **document-search**: Search downloaded files locally

## Best Practices

1. **增量更新**：定期同步时使用 `--incremental` 参数，避免重复下载
2. **重要文件备份**：对关键下载内容保持备份
3. **定期清理**：定期清理旧的下载文件，节省存储空间
4. **结构化组织**：使用 `--organize-by-category` 或 `--organize-by-topic` 保持良好的文件结构
5. **错误重试**：网络不稳定时，脚本会自动重试（默认3次）
6. **Token安全**：不要将token提交到公共代码仓库，config.py应加入.gitignore
7. **智能体管理**：定期检查腾讯元器平台的智能体状态和知识库更新
8. **批量操作**：多个问题时，使用 `--query-file` 批量处理更高效

## 官方资源

### 腾讯IMA产品
- **官网**：https://ima.qq.com
- **电脑端下载**：https://ima.qq.com/download
- **小程序**：搜索「ima知识库」

### 腾讯元器（低代码平台）
- **平台地址**：https://yuanqi.tencent.com
- **API文档**：在智能体→调用API页面查看
- **模型额度**：平台左侧菜单查看当前使用量

### WeKnora（开源框架）
- **GitHub仓库**：https://github.com/Tencent/WeKnora
- **官方文档**：https://docs.opencloudos.org/OC9/ai-deployment/ai-application-practice/weknora-model-deployment/
- **社区支持**：GitHub Issues页面

## 高级用法

### 流式响应处理

```python
from codebuddy.skills.ima_knowledge_base.scripts.search_ima import stream_chat

# 流式对话，实时显示回复
for chunk in stream_chat("解释一下Transformer架构"):
    print(chunk, end='', flush=True)
```

### 自定义插件集成

腾讯元器支持自定义插件，可以扩展知识库能力：

1. 在元器平台创建插件
2. 插件可以调用外部API
3. 绑定到智能体
4. 通过API调用插件功能

### 工作流自动化

使用元器的工作流功能编排复杂任务：

1. 添加知识库节点
2. 添加大模型节点
3. 添加插件节点
4. 设置节点间的数据流
5. 通过API触发工作流

## 常见问题（FAQ）

### Q1: 腾讯IMA知识库和元器的区别是什么？
A: IMA是客户端工具，主要用于个人使用；元器是开发平台，支持API调用和智能体创建。本技能基于元器API。

### Q2: 知识库支持哪些文件格式？
A: 腾讯元器知识库支持doc、docx、txt、PDF四种格式。图片可以通过OCR识别。

### Q3: API调用的免费额度是多少？
A: 腾讯赠送1亿token额度，足够数百万次对话使用。

### Q4: 可以同时接入多个知识库吗？
A: 可以，一个智能体可以绑定多个知识库，回答时会综合检索。

### Q5: 如何在本地使用IMA知识库？
A: 建议使用WeKnora开源框架本地部署，提供完整的REST API。

### Q6: API调用的响应速度如何？
A: 通常在1-3秒内响应，使用流式模式可以更快显示部分结果。

### Q7: 腾讯元器不可用时怎么办？
A: 使用IMA客户端备份工作流：
   - 运行 `python scripts/quick_backup.py`
   - 自动打开本地IMA客户端
   - 手动导出知识库文件
   - 详细说明见 USAGE.md

### Q8: IMA客户端路径在哪里？
A: 常见路径：
   - `C:\Users\qu\AppData\Local\Programs\IMA\ima.exe`
   - `C:\Program Files\IMA\ima.exe`
   - 可设置环境变量 `IMA_EXE_PATH` 或使用 `--ima-path` 参数

### Q9: 如何自动化IMA备份？
A: 使用以下脚本：
   - `quick_backup.py`：交互式快速备份
   - `backup_to_ima.py`：自动检测并备份
   - `ima_gui_automation.py`：GUI自动化操作

## 版本历史

- **v1.0** (2026-03-15): 初始版本，支持腾讯元器API接入
  - 问答功能
  - 文档提取
  - 增量同步
