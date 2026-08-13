# PDF到IMA知识库自动化工作流

## 概述

完整自动化工作流：PDF文件 → 验证 → 扫描 → 处理 → 上传指南 → 启动IMA客户端

## 功能特性

✅ **完整流程**
- PDF文件验证
- 自动提取文件信息
- 生成知识库条目（JSON格式）
- 生成详细上传指南（TXT格式）
- 自动启动IMA客户端

✅ **智能处理**
- 自动从文件名提取标签
- 支持自定义标签和描述
- 自动计算文件大小
- 生成时间戳和元数据

✅ **用户友好**
- 详细的操作指南
- 快捷命令提示
- 完整的错误处理
- 日志记录功能

## 文件说明

### 核心脚本

| 文件 | 说明 |
|------|------|
| `pdf_to_ima_final.py` | 最终版完整工作流脚本 |
| `ima_macro_workflow.py` | IMA客户端启动脚本 |
| `pdf_to_ima_workflow.py` | 原始工作流脚本（包含更多功能） |

### 测试脚本

| 文件 | 说明 |
|------|------|
| `simple_pdf_test.py` | 简化测试脚本 |
| `direct_workflow_test.py` | 直接工作流测试 |

## 使用方式

### 方式1：修改脚本参数（推荐）

1. 编辑 `pdf_to_ima_final.py`

2. 在脚本底部添加：

```python
if __name__ == "__main__":
    # 配置参数
    pdf_path = r"C:\path\to\your\file.pdf"
    ima_path = r"F:\ima.copilot\ima.copilot.exe"
    tags = ["PDF", "文档", "数学"]
    description = "文档描述"

    # 创建工作流
    workflow = PDFToIMAWorkflow(
        pdf_path=pdf_path,
        ima_exe_path=ima_path
    )

    # 准备知识库条目
    workflow.prepare_kb_entry(tags=tags, description=description)

    # 生成上传指南
    workflow.generate_upload_guide()

    # 启动IMA客户端
    workflow.launch_ima()

    print("[OK] 工作流完成！")
```

3. 运行脚本：

```bash
python .codebuddy/skills/ima-knowledge-base/scripts/pdf_to_ima_final.py
```

### 方式2：使用Python API

```python
import sys
import os

# 添加路径
claw_root = r"C:\Users\qu\WorkBuddy\Claw"
sys.path.insert(0, os.path.join(claw_root, '.codebuddy', 'skills', 'ima-knowledge-base', 'scripts'))

from pdf_to_ima_final import PDFToIMAWorkflow

# 创建工作流
workflow = PDFToIMAWorkflow(
    pdf_path=r"C:\path\to\file.pdf",
    ima_exe_path=r"F:\ima.copilot\ima.copilot.exe"
)

# 运行工作流
success = workflow.run()
```

### 方式3：使用测试脚本

1. 编辑 `temp/simple_pdf_test.py` 或 `temp/direct_workflow_test.py`

2. 修改PDF路径：

```python
pdf_path = r"C:\path\to\your\file.pdf"
ima_path = r"F:\ima.copilot\ima.copilot.exe"
```

3. 运行：

```bash
python temp/simple_pdf_test.py
```

## 配置参数

### PDF路径
- 必填参数
- 支持绝对路径或相对路径
- 文件必须是PDF格式

### IMA客户端路径
- 可选参数
- 默认：不自动启动（手动启动）
- 推荐：`F:\ima.copilot\ima.copilot.exe`

### 标签（Tags）
- 可选参数
- 用途：知识库分类和搜索
- 示例：`["PDF", "文档", "数学", "教材"]`

### 描述（Description）
- 可选参数
- 用途：文档说明
- 示例：`"高等代数教科书 - 第五版"`

## 输出文件

运行成功后，会生成以下文件：

### 1. 知识库条目（JSON）

```json
{
  "title": "文件名",
  "type": "PDF文档",
  "file_path": "完整路径",
  "file_size": 文件大小,
  "tags": ["标签1", "标签2"],
  "description": "文档描述",
  "created_time": "创建时间",
  "processed_time": "处理时间"
}
```

### 2. 上传指南（TXT）

包含：
- 文档信息
- 详细上传步骤
- 快捷键说明
- 常见问题解答
- 提示和建议

### 3. 日志文件

记录工作流执行过程：
- 时间戳
- 执行步骤
- 成功/失败状态
- 错误信息

## 工作流步骤

```
步骤1：验证PDF
  ├─ 检查文件是否存在
  ├─ 验证PDF格式
  └─ 获取文件大小

步骤2：准备知识库条目
  ├─ 提取文件信息
  ├─ 生成标签
  ├─ 创建描述
  └─ 保存JSON文件

步骤3：生成上传指南
  ├─ 编写操作步骤
  ├─ 添加快捷键说明
  ├─ 包含常见问题
  └─ 保存TXT文件

步骤4：启动IMA客户端（可选）
  ├─ 启动IMA应用
  ├─ 等待加载完成
  └─ 提示用户操作
```

## 实际示例

### 示例1：数学教材

```python
workflow = PDFToIMAWorkflow(
    pdf_path=r"C:\Users\qu\Desktop\高等代数 第五版.pdf",
    ima_exe_path=r"F:\ima.copilot\ima.copilot.exe"
)

workflow.prepare_kb_entry(
    tags=["PDF", "文档", "数学", "高等代数", "第五版", "教材"],
    description="高等代数教科书 - 第五版 - 北大数学系"
)

workflow.generate_upload_guide()
workflow.launch_ima()
```

### 示例2：技术文档

```python
workflow = PDFToIMAWorkflow(
    pdf_path=r"C:\Downloads\API_Documentation.pdf",
    ima_exe_path=r"F:\ima.copilot\ima.copilot.exe"
)

workflow.prepare_kb_entry(
    tags=["PDF", "技术文档", "API", "开发"],
    description="API接口文档 v2.0"
)

workflow.generate_upload_guide()
```

### 示例3：学术论文

```python
workflow = PDFToIMAWorkflow(
    pdf_path=r"C:\Papers\Research_Paper.pdf",
    ima_exe_path=r"F:\ima.copilot\ima.copilot.exe"
)

workflow.prepare_kb_entry(
    tags=["PDF", "学术论文", "研究", "计算机"],
    description="计算机科学研究论文 - 2026年"
)

workflow.generate_upload_guide()
```

## 故障排除

### 问题1：PDF文件不存在

**解决方案：**
- 检查文件路径是否正确
- 使用绝对路径而非相对路径
- 确认文件扩展名为 `.pdf`

### 问题2：IMA客户端启动失败

**解决方案：**
- 检查IMA客户端路径是否正确
- 确认IMA客户端已正确安装
- 手动启动IMA客户端

### 问题3：编码错误

**解决方案：**
- 确保使用UTF-8编码
- 避免使用特殊字符和emoji
- 使用ASCII兼容的文件名

### 问题4：权限错误

**解决方案：**
- 以管理员身份运行脚本
- 检查文件夹权限
- 确保有写入权限

## 快捷命令

```bash
# 查看输出目录
explorer c:\Users\qu\WorkBuddy\Claw\ima_backups\processed_pdfs

# 查看知识库条目
type kb_entry_*.json

# 查看上传指南
type upload_guide_*.txt

# 查看日志
type ima_backups\pdf_to_ima_workflow_log.txt
```

## 高级用法

### 批量处理

```python
import os
from pdf_to_ima_final import PDFToIMAWorkflow

pdf_dir = r"C:\PDFs"
ima_path = r"F:\ima.copilot\ima.copilot.exe"

for filename in os.listdir(pdf_dir):
    if filename.endswith('.pdf'):
        pdf_path = os.path.join(pdf_dir, filename)
        workflow = PDFToIMAWorkflow(pdf_path, ima_path)
        workflow.run()
```

### 自定义处理

```python
from pdf_to_ima_final import PDFToIMAWorkflow

workflow = PDFToIMAWorkflow(pdf_path)
workflow.validate_pdf()
workflow.prepare_kb_entry(tags=["自定义标签"])

# 自定义处理...
custom_process(workflow)

workflow.generate_upload_guide()
```

## 相关文档

- [IMA知识库集成](../SKILL.md)
- [IMA宏工作流](./ima_macro_workflow.py)
- [备份工作流](./backup_to_ima.py)
- [主README](../../../../../README.md)

## 更新日志

### v1.0 (2026-03-15)
- ✅ 完整工作流实现
- ✅ PDF验证和处理
- ✅ 知识库条目生成
- ✅ 上传指南生成
- ✅ IMA客户端自动启动
- ✅ 完整日志记录
- ✅ 错误处理机制

## 联系支持

如有问题，请查看：
- 日志文件：`ima_backups/pdf_to_ima_workflow_log.txt`
- 错误信息：运行时的控制台输出
- 常见问题：上传指南中的"常见问题"部分
