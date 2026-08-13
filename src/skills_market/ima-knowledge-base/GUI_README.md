# IMA GUI管理器使用指南

## 简介

IMA GUI管理器是一个图形化界面工具，方便用户操作IMA知识库。

## 功能特点

### 1. 知识库搜索
- 向腾讯元器知识库提问
- 实时显示AI回答
- 支持复制和保存结果

### 2. 备份工作流
- **自动检测模式**：优先使用腾讯元器API，失败时自动打开IMA客户端
- **强制使用IMA客户端**：跳过API检测，直接打开本地IMA客户端
- **仅打开IMA客户端**：仅打开应用，不执行备份操作

## 使用方法

### 启动GUI

从Claw根目录运行：

```bash
cd c:\Users\qu\WorkBuddy\Claw
python .codebuddy\skills\ima-knowledge-base/ima_gui.py
```

或者创建快捷方式：
1. 创建 `ima_gui.bat` 文件
2. 内容：`python c:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\ima_gui.py`
3. 双击即可启动

### 知识库搜索

1. 切换到"知识库搜索"标签页
2. 输入问题
3. 点击"搜索"按钮
4. 等待结果显示
5. 可以：
   - 清空结果：清空搜索框
   - 复制结果：复制到剪贴板
   - 保存结果：保存为文本文件

### 备份工作流

#### 配置IMA客户端路径

1. 切换到"备份工作流"标签页
2. 点击"浏览..."选择IMA客户端（ima.exe）
3. 常见位置：
   - `C:\Users\qu\AppData\Local\Programs\IMA\ima.exe`
   - `C:\Program Files\IMA\ima.exe`
   - `C:\Program Files (x86)\IMA\ima.exe`

#### 选择备份模式

**自动检测（推荐）**
- 先尝试连接腾讯元器API
- API可用时使用API备份
- API不可用时自动打开IMA客户端

**强制使用IMA客户端**
- 跳过API检测
- 直接打开IMA客户端进行手动备份

**仅打开IMA客户端**
- 不执行任何备份操作
- 仅打开IMA客户端供手动操作

#### 执行备份

1. 选择备份模式
2. 点击"开始备份"按钮
3. 观察日志输出

## 常见问题

### Q1: GUI启动失败
**A**: 检查Python环境：
- 确保Python 3.6+已安装
- 检查tkinter库是否可用：`python -c "import tkinter"`

### Q2: 搜索失败
**A**: 检查API配置：
- 编辑 `.codebuddy/skills/ima-knowledge-base/config.py`
- 填写 `YUANQI_ASSISTANT_ID` 和 `YUANQI_TOKEN`
- 获取方式：https://yuanqi.tencent.com/ → 我的创建 → 智能体 → 更多 → 调用API

### Q3: IMA客户端找不到
**A**: 手动指定路径：
- 点击"浏览..."选择IMA客户端
- 或设置环境变量：`set IMA_EXE_PATH=C:\path\to\ima.exe`

### Q4: 备份目录没有创建
**A**: 检查权限：
- 确保有C盘的写入权限
- 备份目录：`C:\Users\qu\WorkBuddy\Claw\ima_backups`

## 技术细节

### 项目结构

```
.codebuddy/skills/ima-knowledge-base/
├── ima_gui.py              # GUI主程序
├── path_helper.py           # 路径管理
├── config.py               # API配置
└── scripts/
    ├── search_ima.py        # 搜索模块
    ├── backup_to_ima.py     # 备份工作流
    └── ...
```

### 依赖模块

- **tkinter**: GUI框架（Python内置）
- **threading**: 多线程支持
- **path_helper**: 统一路径管理
- **search_ima**: 腾讯元器API
- **backup_to_ima**: 备份工作流

### 多线程设计

GUI使用多线程避免界面冻结：
- 搜索操作在后台线程执行
- 备份操作在后台线程执行
- 连接测试在后台线程执行
- UI通过 `root.after()` 更新

## 快捷键和操作

| 操作 | 说明 |
|------|------|
| Ctrl+C | 复制选中文本 |
| Ctrl+A | 全选文本 |
| 浏览按钮 | 打开文件选择器 |
| 打开按钮 | 打开备份目录 |

## 配置示例

### config.py 示例

```python
# 腾讯元器API配置
YUANQI_BASE_URL = "https://yuanqi.tencent.com/api/v1/chat"
YUANQI_ASSISTANT_ID = "your_assistant_id_here"
YUANQI_TOKEN = "your_token_here"
YUANQI_USER_ID = "default_user"
```

## 更新日志

### 2026-03-15
- ✓ 创建IMA GUI管理器
- ✓ 实现知识库搜索功能
- ✓ 实现备份工作流界面
- ✓ 添加多线程支持
- ✓ 修复路径导入问题
- ✓ 添加Windows控制台编码支持
- ✓ 测试通过，GUI正常启动
