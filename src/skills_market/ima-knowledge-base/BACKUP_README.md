# IMA知识库备份工作流

## 📋 概述

当腾讯元器不可用时，自动打开本地IMA客户端进行知识库备份操作。

## 🎯 功能特点

- ✅ **自动检测**：先尝试腾讯元器API，不可用时自动切换到IMA客户端
- ✅ **弹窗执行**：使用可见窗口，符合shell-logging规则
- ✅ **日志记录**：记录所有备份操作
- ✅ **灵活配置**：支持环境变量和命令行参数
- ✅ **交互式**：提供友好的操作提示

## 🚀 快速开始

### 1. 配置IMA路径

**方法1：环境变量（推荐）**

```bash
# Windows PowerShell
$env:IMA_EXE_PATH = "C:\Users\qu\AppData\Local\Programs\IMA\ima.exe"

# 永久设置（PowerShell）
[Environment]::SetEnvironmentVariable("IMA_EXE_PATH", "C:\Users\qu\AppData\Local\Programs\IMA\ima.exe", "User")
```

**方法2：命令行参数**

```bash
python scripts/backup_to_ima.py --ima-path "C:\path\to\ima.exe"
```

### 2. 运行备份

**快速备份（推荐）：**

```bash
python scripts/quick_backup.py
```

**自动检测模式：**

```bash
python scripts/backup_to_ima.py
```

**强制使用IMA：**

```bash
python scripts/backup_to_ima.py --force-ima
```

**仅打开IMA：**

```bash
python scripts/ima_gui_automation.py --open-only
```

## 📁 脚本说明

### 1. quick_backup.py - 快速备份入口

**功能：** 交互式快速备份，提供3种模式选择

**使用：**
```bash
python scripts/quick_backup.py
```

**选项：**
1. 自动检测（推荐）
2. 强制使用IMA客户端
3. 仅打开IMA客户端

### 2. backup_to_ima.py - 备份工作流

**功能：** 完整的备份工作流，自动检测元器连接

**使用：**
```bash
# 自动检测模式
python scripts/backup_to_ima.py

# 强制使用IMA
python scripts/backup_to_ima.py --force-ima

# 指定IMA路径
python scripts/backup_to_ima.py --ima-path "C:\path\to\ima.exe"

# 仅测试连接
python scripts/backup_to_ima.py --test-connection
```

**参数：**
- `--force-ima, -f`：强制使用IMA客户端
- `--ima-path, -p`：指定IMA客户端路径
- `--test-connection, -t`：仅测试腾讯元器连接

### 3. ima_gui_automation.py - GUI自动化

**功能：** IMA客户端GUI自动化操作

**使用：**
```bash
# 仅打开IMA
python scripts/ima_gui_automation.py --open-only

# 尝试自动化操作
python scripts/ima_gui_automation.py --auto

# 指定路径
python scripts/ima_gui_automation.py --ima-path "C:\path\to\ima.exe"
```

**依赖（可选）：**
```bash
pip install pywinauto pyautogui
```

## 🔄 工作流程

```
开始
  ↓
检测腾讯元器连接
  ↓
  ├─ 可用 → 提示使用元器API（功能更完整）
  │
  └─ 不可用 → 打开IMA客户端
              ↓
              显示操作提示
              ↓
              用户手动导出文件
              ↓
              记录备份日志
              ↓
              完成
```

## 📂 备份目录结构

```
ima_backups/
├── backup_log.json      # 备份日志
└── [用户导出的文件]     # 手动导出的知识库文件
```

## 📝 备份日志格式

```json
{
  "backups": [
    {
      "timestamp": "2026-03-15T14:30:00",
      "mode": "ima_client",
      "ima_path": "C:\\Users\\qu\\AppData\\Local\\Programs\\IMA\\ima.exe",
      "backup_dir": "C:\\Users\\qu\\WorkBuddy\\Claw\\ima_backups"
    }
  ]
}
```

## 🎨 使用示例

### 示例1：日常快速备份

```bash
# 运行快速备份，选择模式1（自动检测）
python scripts/quick_backup.py
```

输出：
```
================================================================================
IMA知识库快速备份
================================================================================

✓ 找到IMA客户端: C:\Users\qu\AppData\Local\Programs\IMA\ima.exe

请选择备份模式:
  1. 自动检测（推荐）
     - 先尝试腾讯元器API
     - 不可用时打开IMA客户端

  2. 强制使用IMA客户端
     - 跳过元器检测，直接打开IMA

  3. 仅打开IMA客户端
     - 不执行备份，只打开应用

请输入选项 (1-3，默认1): 1

模式: 自动检测
```

### 示例2：强制使用IMA

```bash
python scripts/backup_to_ima.py --force-ima
```

输出：
```
================================================================================
IMA知识库备份工作流
================================================================================
时间: 2026-03-15 14:30:00
备份目录: C:\Users\qu\WorkBuddy\Claw\ima_backups
================================================================================

步骤1: 强制使用IMA客户端（跳过元器检查）

步骤2: 打开IMA客户端进行备份...
✓ 找到IMA客户端: C:\Users\qu\AppData\Local\Programs\IMA\ima.exe
正在打开IMA客户端: C:\Users\qu\AppData\Local\Programs\IMA\ima.exe
================================================================================
✓ IMA客户端已打开

请在IMA客户端中进行以下操作:
  1. 登录（如果需要）
  2. 打开个人知识库
  3. 选择需要备份的文件/文件夹
  4. 右键 → 下载/导出到本地
  5. 保存到备份目录:
     C:\Users\qu\WorkBuddy\Claw\ima_backups

操作完成后，按任意键关闭此窗口...
```

### 示例3：仅测试连接

```bash
python scripts/backup_to_ima.py --test-connection
```

输出：
```
测试腾讯元器连接...
✗ 连接失败
  请检查config.py中的YUANQI_ASSISTANT_ID和YUANQI_TOKEN
```

## 🔍 IMA客户端手动操作指南

当IMA客户端打开后，请按以下步骤操作：

### 1. 登录（首次使用）

- 使用微信扫码登录
- 或使用手机号登录

### 2. 打开知识库

- 点击左侧「知识库」或「个人知识库」
- 进入知识库界面

### 3. 选择文件

**单选：**
- 点击单个文件

**多选：**
- 按住Ctrl键点击多个文件
- 或按住Shift键选择连续文件

**全选：**
- 按 Ctrl+A 全选所有文件

### 4. 导出文件

- 右键点击选中的文件
- 选择「下载」或「导出」
- 选择保存位置：`C:\Users\qu\WorkBuddy\Claw\ima_backups\`
- 点击「保存」

### 5. 完成备份

- 等待下载完成
- 检查文件是否正确保存
- 按任意键关闭提示窗口

## ⚠️ 注意事项

1. **IMA路径**
   - 确保IMA客户端已安装
   - 路径必须正确
   - 建议使用环境变量设置

2. **备份目录**
   - 默认：`C:\Users\qu\WorkBuddy\Claw\ima_backups`
   - 确保有足够的磁盘空间
   - 定期清理旧备份

3. **元器配置**
   - 如果配置了元器API，会优先使用元器
   - 使用 `--force-ima` 强制使用IMA
   - 元器功能更完整，建议优先使用

4. **GUI自动化**
   - 需要安装依赖：`pip install pywinauto pyautogui`
   - 自动化功能需要根据IMA版本调整
   - 建议使用手动操作模式（默认）

## 🐛 故障排除

### 问题1：未找到ima.exe

```
错误: 未找到ima.exe
```

**解决方案：**
1. 下载并安装IMA：https://ima.qq.com/
2. 设置环境变量 `IMA_EXE_PATH`
3. 或使用 `--ima-path` 参数

### 问题2：打开IMA失败

```
✗ 打开IMA客户端失败
```

**解决方案：**
1. 检查IMA是否已正确安装
2. 尝试手动双击打开IMA
3. 检查路径是否正确

### 问题3：元器不可用但不想用IMA

```
✗ 腾讯元器不可用
```

**解决方案：**
1. 检查网络连接
2. 验证API凭证配置
3. 使用 `--force-ima` 强制使用IMA

### 问题4：GUI自动化不工作

```
自动化操作失败
```

**解决方案：**
1. 安装依赖：`pip install pywinauto pyautogui`
2. 使用手动操作模式（默认）
3. 或调整自动化脚本适配IMA版本

## 📊 备份策略建议

### 每日备份

```bash
# 每天凌晨2点自动备份（使用Windows任务计划程序）
python scripts/backup_to_ima.py --force-ima
```

### 每周备份

```bash
# 每周日凌晨3点备份
python scripts/quick_backup.py
```

### 重要操作前备份

```bash
# 在重要操作前先备份
python scripts/quick_backup.py
```

## 🔄 与元器的对比

| 功能 | 腾讯元器 | IMA客户端 |
|------|---------|---------|
| API调用 | ✅ 支持 | ❌ 不支持 |
| 批量问答 | ✅ 支持 | ❌ 不支持 |
| 自动同步 | ✅ 支持 | ❌ 不支持 |
| 本地存储 | ❌ 云端 | ✅ 本地 |
| 离线使用 | ❌ 需要 | ✅ 支持 |
| GUI操作 | ❌ 无 | ✅ 支持 |

**建议：**
- 日常使用腾讯元器API（功能完整）
- 元器不可用时使用IMA客户端（备用方案）

## 📚 相关文档

- [USAGE.md](USAGE.md) - 完整使用指南
- [SKILL.md](SKILL.md) - 技能说明文档
- [README.md](README.md) - 状态报告

## 🎉 总结

IMA知识库备份工作流提供了一个可靠的备用方案，当腾讯元器不可用时，可以自动打开本地IMA客户端进行备份操作。

**特点：**
- ✅ 自动检测元器状态
- ✅ 弹窗执行，符合规则
- ✅ 完整日志记录
- ✅ 灵活配置
- ✅ 友好提示

**适用场景：**
- 元器API不可用
- 需要离线备份
- 手动导出文件
- 定期备份任务

---

**创建时间：** 2026-03-15
**版本：** v1.0
