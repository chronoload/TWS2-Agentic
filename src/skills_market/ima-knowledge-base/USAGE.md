# 腾讯元器知识库技能使用指南

## 📋 概述

本技能提供了一套工具，用于与腾讯元器（Tencent Yuanqi）知识库进行交互，包括问答、内容提取和同步功能。

## 🔧 配置说明

### 1. 获取API凭证

在使用本技能之前，需要先从腾讯元器平台获取API凭证：

1. 访问 https://yuanqi.tencent.com/
2. 点击「我的创建」
3. 找到你的智能体，点击「更多」→「调用API」
4. 复制以下信息：
   - **url**: API调用地址（通常为 `https://yuanqi.tencent.com/api/v1/chat`）
   - **assistant_id**: 智能体ID
   - **token**: 认证令牌

### 2. 配置文件

编辑 `config.py` 文件，填入获取的凭证：

```python
# 腾讯元器API配置
YUANQI_BASE_URL = "https://yuanqi.tencent.com/api/v1/chat"  # API地址
YUANQI_ASSISTANT_ID = "your_assistant_id_here"              # 智能体ID
YUANQI_TOKEN = "your_token_here"                          # 认证令牌
YUANQI_USER_ID = "default_user"                            # 用户ID
```

### 3. 环境变量（可选）

也可以通过环境变量设置，优先级高于配置文件：

```bash
# Windows PowerShell
$env:YUANQI_ASSISTANT_ID = "your_assistant_id"
$env:YUANQI_TOKEN = "your_token"

# Linux/Mac
export YUANQI_ASSISTANT_ID="your_assistant_id"
export YUANQI_TOKEN="your_token"
```

## 🚀 使用方法

### 1. 问答脚本 (search_ima.py)

向知识库提问并获取AI回答。

#### 基本用法

```bash
# 单个问答
python scripts/search_ima.py --query "什么是机器学习？"

# 保存回答到文件
python scripts/search_ima.py --query "Python编程技巧" --output answer.json

# 显示原始JSON响应
python scripts/search_ima.py --query "深度学习基础" --show-json
```

#### 流式响应

```bash
# 使用流式响应，实时显示回答
python scripts/search_ima.py --query "Transformer架构" --stream
```

#### 批量问答

```bash
# 从文件批量读取问题
echo -e "什么是RESTful API？\n如何设计数据库？" > questions.txt
python scripts/search_ima.py --query-file questions.txt --output batch_results.json
```

### 2. 内容提取脚本 (download_ima.py)

从知识库中提取并保存相关文档内容。

#### 基本用法

```bash
# 提取内容并显示
python scripts/download_ima.py --query "请列出所有关于微服务架构的文档内容"

# 提取并保存为文档
python scripts/download_ima.py --query "总结Vue.js最佳实践" --save-docs

# 提取并按主题组织
python scripts/download_ima.py --query "机器学习知识点" --save-docs --organize
```

#### 包含引用

```bash
# 提取内容并包含文档引用
python scripts/download_ima.py --query "React组件开发指南" --save-docs --include-references
```

### 3. 同步脚本 (sync_ima.py)

定期同步知识库内容到本地存储。

#### 基本用法

```bash
# 全量同步
python scripts/sync_ima.py --query "Python编程" --full

# 增量同步（24小时内未同步的）
python scripts/sync_ima.py --query "机器学习" --incremental

# 按类别组织
python scripts/sync_ima.py --query "Web开发" --organize
```

#### 自定义查询数量

```bash
# 生成20个查询问题进行同步
python scripts/sync_ima.py --query "数据科学" --num-queries 20
```

#### 查看同步状态

```bash
# 显示同步历史和统计信息
python scripts/sync_ima.py --status
```

## 📁 文件组织

下载的内容默认保存在 `knowledge_base_downloads/` 目录下：

```
knowledge_base_downloads/
├── 20260315_120000_Python编程.md          # 单个问答文档
├── sync_20260315_120000_Python编程.json   # 批量同步结果
├── Python编程/                             # 按类别组织的目录
│   ├── 01_Python编程.md
│   ├── 02_Python编程.md
│   └── ...
├── 机器学习/
│   ├── 01_机器学习.md
│   └── ...
└── sync_state.json                         # 同步状态记录
```

## 🔍 典型使用场景

### 场景1：研究主题调研

```bash
# 1. 先用问答了解主题
python scripts/search_ima.py --query "深度学习的发展历程"

# 2. 提取详细内容并保存
python scripts/download_ima.py --query "深度学习核心技术" --save-docs --organize

# 3. 批量生成相关问题并同步
python scripts/sync_ima.py --query "深度学习" --num-queries 15 --organize
```

### 场景2：项目文档收集

```bash
# 同步项目相关文档
python scripts/sync_ima.py --query "项目需求文档" --organize

# 查询具体问题
python scripts/search_ima.py --query "用户认证流程"

# 提取并保存API文档
python scripts/download_ima.py --query "REST API接口说明" --save-docs
```

### 场景3：学习资料整理

```bash
# 批量问答，保存学习笔记
echo -e "什么是闭包？\nPython装饰器原理？" > python_questions.txt
python scripts/search_ima.py --query-file python_questions.txt --output python_notes.json

# 定期同步新内容
python scripts/sync_ima.py --query "Python进阶" --incremental
```

## ⚠️ 注意事项

1. **API限制**
   - 腾讯元器提供1亿token免费额度
   - 注意调用频率，避免超限

2. **配置安全**
   - 不要将token提交到公共代码仓库
   - 建议将config.py添加到.gitignore

3. **网络要求**
   - 需要稳定的网络连接
   - 首次使用建议测试单个问答

4. **内容质量**
   - 知识库内容质量取决于上传的文档
   - 提示词越具体，回答越准确

## 🐛 故障排除

### 问题1：认证失败

```
错误: 请先配置YUANQI_ASSISTANT_ID和YUANQI_TOKEN
```

**解决方案**：
1. 确认在config.py中正确配置了ID和token
2. 检查token是否过期（重新从平台获取）
3. 确认智能体已发布（未发布的智能体无法调用API）

### 问题2：网络连接失败

```
错误: API调用失败: ConnectionError
```

**解决方案**：
1. 检查网络连接
2. 确认API地址正确
3. 检查防火墙设置

### 问题3：响应超时

```
错误: API调用失败: Timeout
```

**解决方案**：
1. 在config.py中增加`REQUEST_TIMEOUT`值
2. 简化问题，减少复杂度
3. 检查网络稳定性

### 问题4：JSON解析错误

```
错误: 解析回答失败
```

**解决方案**：
1. 使用`--show-json`查看原始响应
2. 检查API响应格式是否正确
3. 联系腾讯元器技术支持

---

## 💾 IMA知识库备份工作流

当腾讯元器不可用时，可以使用本地IMA客户端进行备份操作。

### 配置IMA客户端路径

**方法1：设置环境变量（推荐）**
```bash
# Windows PowerShell
$env:IMA_EXE_PATH = "C:\Users\qu\AppData\Local\Programs\IMA\ima.exe"

# Linux/Mac
export IMA_EXE_PATH="/path/to/ima.exe"
```

**方法2：通过命令行参数**
```bash
python scripts/backup_to_ima.py --ima-path "C:\path\to\ima.exe"
```

### 使用方法

#### 快速备份（推荐）

```bash
# 交互式快速备份
python scripts/quick_backup.py
```

这会提供3个选项：
1. **自动检测**（推荐）：先尝试腾讯元器API，不可用时打开IMA客户端
2. **强制使用IMA**：跳过元器检测，直接打开IMA客户端
3. **仅打开IMA**：不执行备份，只打开应用

#### 备份工作流

```bash
# 自动检测模式
python scripts/backup_to_ima.py

# 强制使用IMA客户端
python scripts/backup_to_ima.py --force-ima

# 指定IMA路径
python scripts/backup_to_ima.py --ima-path "C:\path\to\ima.exe"

# 仅测试连接
python scripts/backup_to_ima.py --test-connection
```

#### GUI自动化

```bash
# 仅打开IMA客户端
python scripts/ima_gui_automation.py --open-only

# 尝试自动化操作（需要根据IMA版本调整）
python scripts/ima_gui_automation.py --auto

# 指定IMA路径
python scripts/ima_gui_automation.py --ima-path "C:\path\to\ima.exe"
```

### 备份流程

1. **检测腾讯元器连接**
   - 检查API凭证配置
   - 测试连接状态

2. **元器不可用时**
   - 自动打开本地IMA客户端
   - 显示操作提示
   - 用户在IMA界面手动导出文件

3. **备份目录**
   ```
   C:\Users\qu\WorkBuddy\Claw\ima_backups/
   ├── backup_log.json      # 备份日志
   └── [导出的文件]         # 用户手动导出的文件
   ```

### 手动操作指南

当IMA客户端打开后，请执行以下操作：

1. **登录**（如果需要）
   - 使用微信扫码登录

2. **打开知识库**
   - 点击左侧「知识库」或「个人知识库」

3. **选择文件**
   - 单选：点击单个文件
   - 多选：Ctrl+点击选择多个文件
   - 全选：Ctrl+A选择所有文件

4. **导出文件**
   - 右键点击选中的文件
   - 选择「下载」或「导出」
   - 选择保存位置：`C:\Users\qu\WorkBuddy\Claw\ima_backups\`

5. **完成备份**
   - 等待下载完成
   - 按任意键关闭提示窗口

### 常见IMA路径

```bash
# Windows常见安装路径
C:\Users\qu\AppData\Local\Programs\IMA\ima.exe
C:\Program Files\IMA\ima.exe
C:\Program Files (x86)\IMA\ima.exe
C:\Users\qu\Desktop\ima.exe
C:\Users\qu\Downloads\ima.exe

# 查找IMA路径
where ima.exe  # 在命令行中运行
```

### 备份脚本对比

| 脚本 | 用途 | 自动化程度 | 适用场景 |
|------|------|-----------|----------|
| quick_backup.py | 快速备份 | 低（交互式） | 日常使用，灵活选择 |
| backup_to_ima.py | 备份工作流 | 中（自动检测） | 定期备份，集成自动化 |
| ima_gui_automation.py | GUI操作 | 高（可选） | 需要精细控制 |

### 故障排除

**问题：未找到ima.exe**
```
错误: 未找到ima.exe
```

**解决方案**：
1. 检查IMA是否已安装：https://ima.qq.com/
2. 设置环境变量 `IMA_EXE_PATH`
3. 使用 `--ima-path` 参数指定路径

**问题：打开IMA失败**
```
错误: 打开IMA客户端失败
```

**解决方案**：
1. 确认IMA客户端路径正确
2. 尝试手动双击打开IMA
3. 检查是否有权限问题

**问题：腾讯元器不可用但不想用IMA**
```
✗ 腾讯元器不可用
```

**解决方案**：
1. 检查网络连接
2. 验证API凭证配置
3. 使用 `--force-ima` 强制使用IMA

### 最佳实践

1. **定期备份**
   - 建议每周备份一次
   - 使用 `quick_backup.py` 快速备份

2. **混合使用**
   - 日常使用腾讯元器API（功能完整）
   - 元器不可用时使用IMA客户端（备用方案）

3. **日志记录**
   - 备份日志保存在 `ima_backups/backup_log.json`
   - 可查看备份历史

4. **自动化集成**
   - 可集成到定时任务
   - 示例：每天凌晨自动检测并备份

---

## 📚 参考资料

- 腾讯元器官网: https://yuanqi.tencent.com
- 腾讯IMA: https://ima.qq.com
- 腾讯混元大模型: https://cloud.tencent.com/document/product/1729

## 🔄 版本历史

- **v1.0** (2026-03-15): 初始版本
  - 支持单个问答
  - 支持批量问答
  - 支持内容提取和保存
  - 支持增量同步
  - 支持按类别组织
