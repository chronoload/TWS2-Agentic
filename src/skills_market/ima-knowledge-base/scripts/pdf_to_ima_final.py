"""
PDF到IMA知识库自动化工作流（最终版）
完整流程：PDF文件 → 验证 → 扫描 → 处理 → 上传指南 → 启动IMA

使用方式：
    python pdf_to_ima_final.py <PDF路径> [--ima-path <IMA路径>]

示例：
    python pdf_to_ima_final.py "C:\path\to\file.pdf"
    python pdf_to_ima_final.py "C:\path\to\file.pdf" --ima-path "F:\ima.copilot\ima.copilot.exe"
"""
import sys
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path

# Windows控制台编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加路径
current_file = os.path.abspath(__file__)
claw_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))

try:
    sys.path.insert(0, os.path.join(claw_root, '.codebuddy', 'skills', 'ima-knowledge-base'))
    from path_helper import get_ima_backups_dir
except ImportError:
    get_ima_backups_dir = lambda: os.path.join(claw_root, 'ima_backups')


class PDFToIMAWorkflow:
    def __init__(self, pdf_path, ima_exe_path=None):
        self.pdf_path = pdf_path
        self.ima_exe = ima_exe_path
        self.backup_dir = get_ima_backups_dir()
        self.output_dir = os.path.join(self.backup_dir, "processed_pdfs")
        self.log_file = os.path.join(self.backup_dir, "pdf_to_ima_workflow_log.txt")
        self.ensure_dirs()

        # 处理结果
        self.pdf_info = None
        self.kb_entry = None
        self.guide_file = None

    def ensure_dirs(self):
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        print(log_msg)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    def validate_pdf(self):
        """验证PDF文件"""
        if not self.pdf_path:
            self.log("[ERROR] 未指定PDF文件路径", "ERROR")
            return False

        if not os.path.exists(self.pdf_path):
            self.log(f"[ERROR] PDF文件不存在: {self.pdf_path}", "ERROR")
            return False

        if not self.pdf_path.lower().endswith('.pdf'):
            self.log(f"[ERROR] 文件不是PDF格式", "ERROR")
            return False

        pdf_size = os.path.getsize(self.pdf_path)
        self.log(f"[OK] PDF验证通过: {os.path.basename(self.pdf_path)} ({pdf_size/1024/1024:.2f} MB)")
        return True

    def prepare_kb_entry(self, tags=None, description=None):
        """准备知识库条目"""
        self.log("[步骤2] 准备知识库条目...")

        try:
            pdf_name = os.path.basename(self.pdf_path)
            pdf_stem = Path(self.pdf_path).stem
            pdf_size = os.path.getsize(self.pdf_path)

            # 自动提取标签
            auto_tags = ['PDF', '文档']
            if tags:
                auto_tags.extend(tags)
            else:
                # 从文件名中提取可能的标签
                if '高等代数' in pdf_stem or '代数' in pdf_stem:
                    auto_tags.append('数学')
                    auto_tags.append('高等代数')
                if '第五版' in pdf_stem:
                    auto_tags.append('第五版')

            kb_entry = {
                'title': pdf_stem,
                'type': 'PDF文档',
                'file_path': self.pdf_path,
                'file_name': pdf_name,
                'file_size': pdf_size,
                'file_size_mb': round(pdf_size / 1024 / 1024, 2),
                'created_time': datetime.now().isoformat(),
                'processed_time': datetime.now().isoformat(),
                'tags': list(set(auto_tags)),  # 去重
                'description': description or f"PDF文档: {pdf_name}",
                'metadata': {
                    'pages': '未知',
                    'format': 'PDF'
                }
            }

            # 保存知识库条目
            entry_file = os.path.join(
                self.output_dir,
                f"kb_entry_{pdf_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            with open(entry_file, 'w', encoding='utf-8') as f:
                json.dump(kb_entry, f, ensure_ascii=False, indent=2)

            self.log(f"[OK] 知识库条目已保存: {os.path.basename(entry_file)}")
            self.kb_entry = kb_entry
            return True

        except Exception as e:
            self.log(f"[ERROR] 准备知识库条目失败: {e}", "ERROR")
            return False

    def generate_upload_guide(self):
        """生成上传指南"""
        self.log("[步骤3] 生成上传指南...")

        try:
            pdf_name = os.path.basename(self.pdf_path)
            pdf_stem = Path(self.pdf_path).stem

            instructions = f"""
IMA知识库上传完整指南
{'=' * 60}

文档信息
─────────────────
文件名: {pdf_name}
完整路径: {self.pdf_path}
文件大小: {self.kb_entry['file_size']:,} 字节 ({self.kb_entry['file_size_mb']} MB)
标题: {self.kb_entry['title']}
类型: {self.kb_entry['type']}
处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

标签
─────────────────
{', '.join(self.kb_entry['tags'])}

描述
─────────────────
{self.kb_entry['description']}

上传步骤
─────────────────
1. 启动IMA客户端
   双击IMA图标或运行: {self.ima_exe or '手动启动'}

2. 登录IMA账户
   - 使用微信扫码登录
   - 或使用账号密码登录

3. 进入知识库
   - 点击左侧【知识库】菜单
   - 选择目标知识库（或新建）

4. 上传文档
   - 点击【上传】或【添加文档】按钮
   - 选择文件: {pdf_name}
   - 或拖拽文件到上传区域

5. 填写文档信息
   标题: {self.kb_entry['title']}
   描述: {self.kb_entry['description']}
   标签: {', '.join(self.kb_entry['tags'])}

6. 开始上传
   - 点击【上传】按钮
   - 等待上传完成（大文件需要时间）
   - 上传成功后会提示

7. 验证上传
   - 在知识库中查找文档
   - 验证文件大小和内容
   - 测试搜索功能

快捷键
─────────────────
Ctrl+O: 打开文件对话框
Ctrl+S: 保存/提交
Ctrl+F: 搜索文档
F5: 刷新列表

提示
─────────────────
• 大文件上传可能需要5-15分钟
• 上传时请保持网络连接稳定
• 可以批量上传多个文件
• 上传完成后可以设置权限和分类
• 支持PDF、Word、图片等多种格式

常见问题
─────────────────
Q: 上传失败怎么办？
A: 检查网络连接，重试上传，或联系IMA客服

Q: 文件太大怎么办？
A: IMA支持大文件，但可能需要更长时间

Q: 可以批量上传吗？
A: 是的，IMA支持批量上传

Q: 如何管理已上传的文档？
A: 在知识库中可以查看、编辑、删除文档

─────────────────
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
工具版本: PDFToIMA Workflow v1.0
"""

            guide_file = os.path.join(
                self.output_dir,
                f"upload_guide_{pdf_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )

            with open(guide_file, 'w', encoding='utf-8') as f:
                f.write(instructions)

            self.log(f"[OK] 上传指南已保存: {os.path.basename(guide_file)}")
            self.guide_file = guide_file
            return True

        except Exception as e:
            self.log(f"[ERROR] 生成上传指南失败: {e}", "ERROR")
            return False

    def launch_ima(self, wait_seconds=8):
        """启动IMA客户端"""
        self.log("[步骤4] 启动IMA客户端...")

        if not self.ima_exe:
            self.log("[WARN] 未指定IMA客户端路径，请手动启动", "WARN")
            return False

        if not os.path.exists(self.ima_exe):
            self.log(f"[WARN] IMA客户端不存在: {self.ima_exe}", "WARN")
            return False

        try:
            process = subprocess.Popen([self.ima_exe], shell=False)
            self.log(f"[OK] IMA客户端已启动，PID: {process.pid}")
            print(f"等待 {wait_seconds} 秒让应用完全加载...")
            import time
            time.sleep(wait_seconds)
            return True
        except Exception as e:
            self.log(f"[ERROR] 启动IMA客户端失败: {e}", "ERROR")
            return False

    def run(self):
        """运行完整工作流"""
        self.log("=" * 80)
        self.log("PDF到IMA知识库自动化工作流开始")
        self.log("=" * 80)

        # 验证PDF
        if not self.validate_pdf():
            return False

        # 准备知识库条目
        if not self.prepare_kb_entry():
            return False

        # 生成上传指南
        if not self.generate_upload_guide():
            return False

        # 启动IMA客户端
        self.launch_ima()

        # 完成总结
        self.log("=" * 80)
        self.log("[OK] 工作流执行完成")
        self.log("=" * 80)

        print("\n" + "=" * 80)
        print("[OK] 工作流执行完成")
        print("=" * 80)

        print(f"\n输出目录: {self.output_dir}")
        print(f"\n生成的文件:")
        print(f"  1. 知识库条目: {os.path.basename([f for f in os.listdir(self.output_dir) if f.startswith('kb_entry_') and 'pdf_stem' not in f][-1])}")
        print(f"  2. 上传指南: {os.path.basename(self.guide_file)}")

        print(f"\n下一步操作:")
        print(f"  1. 查看上传指南了解详细步骤")
        print(f"  2. 在IMA客户端中按照指南上传文档")
        print(f"  3. 验证上传成功")

        print(f"\n快捷命令:")
        print(f"  打开输出目录: explorer {self.output_dir}")

        print("=" * 80)

        return True


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PDF到IMA知识库自动化工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pdf_to_ima_final.py "C:\\path\\to\\file.pdf"
  python pdf_to_ima_final.py "C:\\path\\to\\file.pdf" --ima-path "F:\\ima.copilot\\ima.copilot.exe"
  python pdf_to_ima_final.py "C:\\path\\to\\file.pdf" --tags 数学 教材 --desc "大学教材"
        """
    )

    parser.add_argument("pdf", help="PDF文件路径")
    parser.add_argument("--ima-path", "-p", help="IMA客户端路径")
    parser.add_argument("--tags", "-t", nargs='+', help="文档标签")
    parser.add_argument("--desc", "-d", help="文档描述")

    args = parser.parse_args()

    # 清理路径
    pdf_path = args.pdf.strip('"').strip("'").strip()
    ima_path = args.ima_path.strip('"').strip("'").strip() if args.ima_path else None

    # 验证PDF
    if not os.path.exists(pdf_path):
        print(f"[ERROR] PDF文件不存在: {pdf_path}")
        sys.exit(1)

    # 创建工作流
    workflow = PDFToIMAWorkflow(
        pdf_path=pdf_path,
        ima_exe_path=ima_path
    )

    # 运行工作流
    success = workflow.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
