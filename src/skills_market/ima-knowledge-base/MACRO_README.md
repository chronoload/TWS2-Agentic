# IMA宏工作流使用指南

## 简介

IMA宏工作流是一个基于Python脚本的自动化工具，用于操作ima.copilot.exe客户端。相比GUI界面，宏工作流更适合需要重复执行或需要记录操作日志的场景。

## 主要特点

### 1. 自动启动IMA客户端
- 自动查找ima.copilot.exe或ima.exe
- 支持手动指定路径
- 支持环境变量配置

### 2. 两种操作模式

**手动模式（默认）**
- 启动IMA后显示详细操作指南
- 生成操作指南文本文件
- 用户按照指南手动操作
- 适合：不熟悉IMA操作流程的用户

**自动模式（需要pyautogui）**
- 尝试使用pyautogui自动化操作
- 适合：熟悉流程且需要重复操作的用户
- 注意：自动化的可靠性取决于IMA版本

### 3. 日志记录
- 所有操作自动记录到日志文件
- 包含时间戳和操作详情
- 便于追踪和问题排查

## 使用方法

### 方式1：使用BAT文件（推荐）

双击运行：
```bash
运行宏工作流.bat
```

### 方式2：使用命令行

基本用法（手动模式）：
```bash
cd c:\Users\qu\WorkBuddy\Claw
python .codebuddy\skills\ima-knowledge-base\scripts\ima_macro_workflow.py
```

指定IMA路径：
```bash
python scripts\ima_macro_workflow.py --ima-path "C:\path\to\ima.copilot.exe"
```

自动模式：
```bash
python scripts\ima_macro_workflow.py --auto
```

仅启动IMA客户端：
```bash
python scripts\ima_macro_workflow.py --only-launch
```

启动后截图：
```bash
python scripts\ima_macro_workflow.py --screenshot
```

组合参数：
```bash
# 自动模式 + 截图
python scripts\ima_macro_workflow.py --auto --screenshot

# 指定路径 + 自动模式
python scripts\ima_macro_workflow.py -p "C:\ima\copilot.exe" -a
```

## 完整备份流程

### 步骤1：启动工作流

```bash
cd c:\Users\qu\WorkBuddy\Claw
python .codebuddy\skills\ima-knowledge-base\scripts\ima_macro_workflow.py
```

### 步骤2：等待IMA启动

脚本会自动：
1. 查找IMA客户端（ima.copilot.exe或ima.exe）
2. 启动应用
3. 等待8秒让应用完全加载
4. 检测窗口（如果安装了pyautogui）

### 步骤3：按照指南操作

**手动模式下**，屏幕会显示操作指南：

```
IMA知识库手动备份指南
=========================

请在IMA客户端中依次执行以下操作：

1. 登录（如果需要）
   - 使用微信扫码登录
   - 确认登录成功

2. 导航到知识库
   - 点击左侧「知识库」或「我的知识库」
   - 等待知识库列表加载

3. 选择要备份的内容
   - 点击目标知识库
   - 全选：Ctrl+A
   - 或逐个选择需要的文件/文件夹

4. 导出/下载
   - 右键点击选中的内容
   - 选择「导出」或「下载」
   - 选择保存位置

5. 保存到指定目录
   - 导航到: C:\Users\qu\WorkBuddy\Claw\ima_backups
   - 点击「保存」
   - 等待导出完成

6. 确认导出
   - 检查ima_backups目录
   - 确认文件已成功导出

提示：
- 可以使用Ctrl+A全选所有内容
- 大量文件可能需要较长时间
- 导出完成后会提示成功或失败
```

### 步骤4：检查备份结果

查看备份目录：
```bash
explorer C:\Users\qu\WorkBuddy\Claw\ima_backups
```

查看操作日志：
```bash
type C:\Users\qu\WorkBuddy\Claw\ima_backups\macro_workflow_log.txt
```

## 配置选项

### IMA客户端路径

**方式1：自动查找**
脚本会在以下位置自动查找：
1. `C:\Users\qu\AppData\Local\Programs\IMA\ima.copilot.exe`
2. `C:\Users\qu\AppData\Local\Programs\IMA\ima.exe`
3. `C:\Program Files\IMA\ima.copilot.exe`
4. `C:\Program Files\IMA\ima.exe`
5. `C:\Users\qu\Desktop\ima.copilot.exe`
6. `C:\Users\qu\Downloads\ima.copilot.exe`

**方式2：使用命令行参数**
```bash
python scripts\ima_macro_workflow.py --ima-path "C:\path\to\ima.copilot.exe"
```

**方式3：设置环境变量**
```bash
# 临时设置（当前session）
set IMA_EXE_PATH=C:\path\to\ima.copilot.exe

# 永久设置（系统环境变量）
setx IMA_EXE_PATH "C:\path\to\ima.copilot.exe"
```

### 自动模式依赖

自动模式需要安装pyautogui：

```bash
pip install pyautogui
```

**注意**：
- pyautogui是可选的
- 没有pyautogui时，自动模式会回退到手动模式
- 手动模式不需要额外依赖

## 命令参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|---------|
| `--ima-path` | `-p` | 指定IMA客户端路径 | 自动查找 |
| `--auto` | `-a` | 自动模式（尝试自动化） | False（手动） |
| `--only-launch` | `-l` | 仅启动IMA客户端 | False |
| `--screenshot` | `-s` | 启动后截图 | False |

## 输出文件

### 日志文件
**位置**：`C:\Users\qu\WorkBuddy\Claw\ima_backups\macro_workflow_log.txt`

**内容示例**：
```
[2026-03-15 10:30:15] 开始IMA知识库备份工作流
[2026-03-15 10:30:15] 启动IMA客户端: C:\Users\qu\AppData\Local\Programs\IMA\ima.copilot.exe
[2026-03-15 10:30:15] [OK] IMA进程已启动，PID: 12345
[2026-03-15 10:30:23] [OK] 操作指南已保存: backup_guide_20260315_103023.txt
[2026-03-15 10:30:23] [OK] 工作流执行完成
```

### 操作指南文件
**位置**：`C:\Users\qu\WorkBuddy\Claw\ima_backups\backup_guide_YYYYMMDD_HHMMSS.txt`

**用途**：
- 保存详细的操作步骤
- 方便离线查看
- 可以作为操作模板

### 截图文件
**位置**：`C:\Users\qu\WorkBuddy\Claw\ima_backups\ima_*.png`

**命名规则**：
- 启动截图：`ima_launch_YYYYMMDD_HHMMSS.png`
- 备份截图：`ima_backup_YYYYMMDD_HHMMSS.png`

## 常见问题

### Q1: 找不到IMA客户端
**A**:
1. 检查是否安装了ima.copilot
2. 使用`--ima-path`参数指定路径
3. 设置环境变量`IMA_EXE_PATH`
4. 确认路径格式正确（使用正斜杠\或双反斜杠\\）

### Q2: 启动后窗口没出现
**A**:
1. 检查Windows任务栏是否有IMA图标
2. 等待更长时间（可修改脚本中的wait_seconds参数）
3. 查看任务管理器确认进程已启动
4. 查看日志文件确认启动状态

### Q3: 自动模式不工作
**A**:
1. 安装pyautogui：`pip install pyautogui`
2. 确认IMA窗口已完全加载
3. 尝试增加等待时间
4. 如仍有问题，使用手动模式

### Q4: 导出文件失败
**A**:
1. 确认有ima_backups目录的写入权限
2. 检查磁盘空间是否充足
3. 尝试少量文件测试导出
4. 查看IMA客户端的错误提示

### Q5: 如何重复执行
**A**:
1. 使用BAT文件双击运行
2. 创建桌面快捷方式指向BAT文件
3. 使用Windows任务计划程序定时运行
4. 编写批处理脚本循环调用

## 高级用法

### 创建桌面快捷方式

1. 右键桌面 → 新建 → 快捷方式
2. 位置输入：`C:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\运行宏工作流.bat`
3. 名称输入：`IMA备份工作流`
4. 完成后双击快捷方式即可运行

### 定时任务

创建Windows计划任务定期执行：

```powershell
# 以管理员身份运行PowerShell
$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "c:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\scripts\ima_macro_workflow.py" `
    -WorkingDirectory "c:\Users\qu\WorkBuddy\Claw"

$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"

Register-ScheduledTask `
    -TaskName "IMA Daily Backup" `
    -Action $action `
    -Trigger $trigger `
    -User "qu"
```

### 组合脚本示例

创建一个完整的备份脚本：

```batch
@echo off
REM IMA每日备份脚本

echo ====================================
echo       IMA 每日备份
echo ====================================
echo.

REM 1. 运行宏工作流
python c:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\scripts\ima_macro_workflow.py

REM 2. 等待用户完成
echo.
echo 操作完成后按任意键继续...
pause >nul

REM 3. 同步日志到微信
echo.
echo 同步日志到微信...
python c:\Users\qu\WorkBuddy\Claw\sync_workflows\sync_log_to_wechat.py

echo.
echo [OK] 备份流程完成
pause
```

## 与GUI版本的对比

| 特性 | 宏工作流 | GUI版本 |
|------|----------|---------|
| 界面类型 | 命令行 | 图形界面 |
| 操作方式 | 脚本自动化 | 鼠标点击 |
| 日志记录 | ✓ 详细 | ✓ 实时 |
| 适用场景 | 批量/自动化 | 交互式/可视化 |
| 依赖 | Python（可选pyautogui） | Python + tkinter |
| 学习成本 | 低（按提示操作） | 中（需要熟悉界面） |

## 技术细节

### 脚本结构

```
ima_macro_workflow.py
├── IMAMacroWorkflow类
│   ├── find_ima_exe()        # 查找IMA客户端
│   ├── launch_ima()           # 启动IMA
│   ├── wait_for_window()       # 等待窗口
│   ├── send_keystrokes()      # 发送按键
│   ├── type_text()            # 输入文本
│   ├── take_screenshot()       # 截图
│   └── backup_knowledge_base_workflow()  # 主工作流
└── main()                   # 入口函数
```

### 多进程设计

- 使用subprocess.Popen启动IMA
- 非阻塞式执行
- 支持获取进程PID
- 可用于进程管理

### 错误处理

- 所有异常都被捕获
- 错误信息记录到日志
- 提供用户友好的错误提示
- 不会因错误而中断程序

## 更新日志

### 2026-03-15
- ✓ 创建IMA宏工作流脚本
- ✓ 实现自动/手动两种模式
- ✓ 添加日志记录功能
- ✓ 支持截图功能
- ✓ 支持自定义IMA路径
- ✓ 创建BAT便捷启动脚本
- ✓ 编写完整使用指南
- ✓ 测试通过，脚本可正常运行
