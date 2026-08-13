"""
PDF到IMA知识库自动化工作流
完整流程：PDF文件 → 目录识别 → 内容提取 → 上传IMA
"""
import sys
import os
import subprocess
import time
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
script_dir = os.path.dirname(current_file)
parent_dir = os.path.dirname(script_dir)
claw_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
toc_tools_dir = os.path.join(claw_root, 'toc_tools')

for path in [script_dir, parent_dir, claw_root, toc_tools_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from path_helper import CLAW_DIR, get_ima_backups_dir
except ImportError:
    claw_root_dir = claw_root
    get_ima_backups_dir = lambda: os.path.join(claw_root_dir, 'ima_backups')


class PDFToIMAMacro:
    def __init__(self, pdf_path=None, ima_exe_path=None):
        self.pdf_path = pdf_path
        self.ima_exe = ima_exe_path
        self.backup_dir = get_ima_backups_dir()
        self.log_file = os.path.join(self.backup_dir, "pdf_to_ima_workflow_log.txt")
        self.output_dir = os.path.join(self.backup_dir, "processed_pdfs")
        self.ensure_dirs()

        # 处理结果
        self.pdf_info = None
        self.toc_data = None
        self.kb_entry = None

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
        """验证PDF文件是否存在"""
        if not self.pdf_path:
            self.log("[ERROR] 未指定PDF文件路径", "ERROR")
            return False

        if not os.path.exists(self.pdf_path):
            self.log(f"[ERROR] PDF文件不存在: {self.pdf_path}", "ERROR")
            return False

        if not self.pdf_path.lower().endswith('.pdf'):
            self.log(f"[ERROR] 文件不是PDF格式: {self.pdf_path}", "ERROR")
            return False

        self.log(f"[OK] PDF文件验证通过: {os.path.basename(self.pdf_path)}")
        return True

    def scan_pdf(self):
        """扫描PDF基本信息"""
        self.log("[步骤1] 扫描PDF基本信息...")

        scan_script = os.path.join(toc_tools_dir, 'scan_pdf.py')
        if not os.path.exists(scan_script):
            self.log(f"[ERROR] scan_pdf.py不存在: {scan_script}", "ERROR")
            return False

        try:
            result = subprocess.run(
                [sys.executable, scan_script, self.pdf_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                self.log("[OK] PDF扫描完成")
                print(result.stdout)
                # 保存扫描结果
                self.save_scan_result(result.stdout)
                return True
            else:
                self.log(f"[ERROR] PDF扫描失败: {result.stderr}", "ERROR")
                return False

        except Exception as e:
            self.log(f"[ERROR] 扫描PDF时出错: {e}", "ERROR")
            return False

    def save_scan_result(self, output):
        """保存扫描结果到JSON"""
        try:
            lines = output.split('\n')
            info = {
                'file': os.path.basename(self.pdf_path),
                'path': self.pdf_path,
                'scan_time': datetime.now().isoformat(),
                'details': output
            }

            result_file = os.path.join(
                self.output_dir,
                f"scan_{Path(self.pdf_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)

            self.log(f"[OK] 扫描结果已保存: {os.path.basename(result_file)}")
            self.pdf_info = info
            return True

        except Exception as e:
            self.log(f"[ERROR] 保存扫描结果失败: {e}", "ERROR")
            return False

    def process_toc(self):
        """处理PDF目录"""
        self.log("[步骤2] 处理PDF目录...")

        # 询问用户是否需要OCR识别
        print("\n目录处理选项：")
        print("1. 使用现有书签（如果有）")
        print("2. OCR识别目录（需要GPU加速）")
        print("3. 跳过目录处理")

        choice = input("\n请选择 (1-3): ").strip()

        if choice == '2':
            return self.ocr_toc()
        elif choice == '1':
            self.log("[INFO] 使用现有书签")
            return self.extract_bookmarks()
        else:
            self.log("[INFO] 跳过目录处理")
            return True

    def extract_bookmarks(self):
        """提取PDF书签"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(self.pdf_path)
            toc = doc.get_toc()

            if not toc:
                self.log("[WARN] PDF没有书签", "WARN")
                return True

            self.log(f"[OK] 找到 {len(toc)} 个书签")

            # 保存书签
            toc_file = os.path.join(
                self.output_dir,
                f"bookmarks_{Path(self.pdf_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )

            with open(toc_file, 'w', encoding='utf-8') as f:
                for level, title, page in toc:
                    indent = "  " * (level - 1)
                    f.write(f"{indent}{title} (页码: {page})\n")

            self.log(f"[OK] 书签已保存: {os.path.basename(toc_file)}")
            doc.close()
            return True

        except ImportError:
            self.log("[WARN] PyMuPDF未安装，无法提取书签", "WARN")
            return True
        except Exception as e:
            self.log(f"[ERROR] 提取书签失败: {e}", "ERROR")
            return False

    def ocr_toc(self):
        """OCR识别目录"""
        self.log("[INFO] 开始OCR识别目录...")

        ocr_script = os.path.join(toc_tools_dir, 'ocr_toc.py')
        if not os.path.exists(ocr_script):
            self.log(f"[ERROR] ocr_toc.py不存在: {ocr_script}", "ERROR")
            return False

        try:
            result = subprocess.run(
                [sys.executable, ocr_script, self.pdf_path, '--gpu'],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                self.log("[OK] OCR识别完成")
                print(result.stdout)
                return True
            else:
                self.log(f"[ERROR] OCR识别失败: {result.stderr}", "ERROR")
                return False

        except Exception as e:
            self.log(f"[ERROR] OCR识别时出错: {e}", "ERROR")
            return False

    def prepare_kb_entry(self):
        """准备知识库条目"""
        self.log("[步骤3] 准备知识库条目...")

        try:
            pdf_name = os.path.basename(self.pdf_path)
            pdf_stem = Path(self.pdf_path).stem

            kb_entry = {
                'title': pdf_stem,
                'type': 'PDF文档',
                'file_path': self.pdf_path,
                'file_size': os.path.getsize(self.pdf_path),
                'created_time': datetime.now().isoformat(),
                'processed_time': datetime.now().isoformat(),
                'tags': ['PDF', '文档'],
                'description': f"PDF文档: {pdf_name}",
                'metadata': {
                    'has_toc': self.toc_data is not None,
                    'scan_info': self.pdf_info
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

    def upload_to_ima(self, method='api'):
        """上传到IMA知识库"""
        self.log(f"[步骤4] 上传到IMA知识库 (方法: {method})...")

        if method == 'api':
            return self.upload_via_api()
        elif method == 'client':
            return self.upload_via_client()
        else:
            self.log(f"[ERROR] 未知的上传方法: {method}", "ERROR")
            return False

    def upload_via_api(self):
        """通过API上传"""
        try:
            # 尝试导入config
            sys.path.insert(0, parent_dir)
            import config

            if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
                self.log("[WARN] API凭证未配置，改用客户端上传", "WARN")
                return self.upload_via_client()

            self.log("[INFO] 使用腾讯元器API上传...")

            # 构建请求
            import requests

            prompt = f"""
请将以下PDF文档添加到知识库：

文档标题: {self.kb_entry['title']}
文件路径: {self.kb_entry['file_path']}
文件大小: {self.kb_entry['file_size']} 字节
描述: {self.kb_entry['description']}
"""

            # 调用API
            response = requests.post(
                config.YUANQI_BASE_URL,
                json={
                    'assistant_id': config.YUANQI_ASSISTANT_ID,
                    'token': config.YUANQI_TOKEN,
                    'user_id': config.YUANQI_USER_ID,
                    'query': prompt
                },
                timeout=config.REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                self.log("[OK] API上传成功")
                self.log(f"[INFO] API响应: {response.json()}")
                return True
            else:
                self.log(f"[WARN] API上传失败: {response.status_code}", "WARN")
                return False

        except Exception as e:
            self.log(f"[WARN] API上传出错: {e}, 改用客户端上传", "WARN")
            return self.upload_via_client()

    def upload_via_client(self):
        """通过IMA客户端上传"""
        self.log("[INFO] 启动IMA客户端进行上传...")

        if not self.ima_exe:
            self.log("[WARN] 未指定IMA客户端路径，请手动上传", "WARN")
            return self.save_upload_instructions()

        try:
            # 启动IMA客户端
            process = subprocess.Popen([self.ima_exe], shell=False)
            self.log(f"[OK] IMA客户端已启动，PID: {process.pid}")

            # 保存上传指南
            return self.save_upload_instructions()

        except Exception as e:
            self.log(f"[ERROR] 启动IMA客户端失败: {e}", "ERROR")
            return False

    def save_upload_instructions(self):
        """保存上传指南"""
        try:
            instructions = f"""
IMA知识库上传指南
{'=' * 50}

文档信息:
- 文件名: {os.path.basename(self.pdf_path)}
- 文件路径: {self.pdf_path}
- 处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

上传步骤:
1. 登录IMA客户端
2. 点击【知识库】菜单
3. 点击【上传】或【添加文档】
4. 选择文件: {self.pdf_path}
5. 填写文档信息:
   - 标题: {Path(self.pdf_path).stem}
   - 描述: {self.kb_entry['description'] if self.kb_entry else 'PDF文档'}
   - 标签: PDF, 文档
6. 点击【上传】
7. 等待上传完成

处理结果:
- 扫描结果: {'✓ 已完成' if self.pdf_info else '✗ 未完成'}
- 目录处理: {'✓ 已完成' if self.toc_data else '✗ 未完成'}
- 知识库条目: {'✓ 已完成' if self.kb_entry else '✗ 未完成'}
"""

            guide_file = os.path.join(
                self.output_dir,
                f"upload_guide_{Path(self.pdf_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )

            with open(guide_file, 'w', encoding='utf-8') as f:
                f.write(instructions)

            self.log(f"[OK] 上传指南已保存: {os.path.basename(guide_file)}")
            print(f"\n{instructions}")
            return True

        except Exception as e:
            self.log(f"[ERROR] 保存上传指南失败: {e}", "ERROR")
            return False

    def run(self, upload_method='auto'):
        """运行完整工作流"""
        self.log("=" * 80)
        self.log("PDF到IMA知识库自动化工作流开始")
        self.log("=" * 80)

        # 验证PDF
        if not self.validate_pdf():
            return False

        # 扫描PDF
        if not self.scan_pdf():
            return False

        # 处理目录
        if not self.process_toc():
            return False

        # 准备知识库条目
        if not self.prepare_kb_entry():
            return False

        # 上传到IMA
        if upload_method == 'auto':
            # 先尝试API，失败则用客户端
            success = self.upload_to_ima(method='api')
            if not success:
                success = self.upload_to_ima(method='client')
        else:
            success = self.upload_to_ima(method=upload_method)

        # 完成总结
        self.log("=" * 80)
        if success:
            self.log("[OK] 工作流执行完成")
            print(f"\n处理结果已保存到: {self.output_dir}")
            print(f"日志文件: {self.log_file}")
        else:
            self.log("[ERROR] 工作流执行失败", "ERROR")
        self.log("=" * 80)

        return success


def main():
    import argparse

    # 使用自定义解析器来处理中文路径
    class CustomArgParser(argparse.ArgumentParser):
        def parse_args(self, args=None, namespace=None):
            # 如果从命令行解析，使用原始参数
            if args is None:
                import shlex
                # 重新解析sys.argv，避免参数分隔问题
                parsed_args = []
                for arg in sys.argv[1:]:
                    if arg.startswith('--') or arg.startswith('-'):
                        parsed_args.append(arg)
                    elif ' ' in arg or '"' in arg or "'" in arg:
                        # 保留带空格的参数
                        parsed_args.append(arg)
                    else:
                        parsed_args.append(arg)
                args = parsed_args

            return super().parse_args(args, namespace)

    parser = CustomArgParser(description="PDF到IMA知识库自动化工作流")
    parser.add_argument("--pdf", "-f", required=True, help="PDF文件路径")
    parser.add_argument("--ima-path", "-p", help="IMA客户端路径")
    parser.add_argument("--upload-method", "-m", choices=['api', 'client', 'auto'],
                       default='auto', help="上传方法 (api/client/auto)")

    args = parser.parse_args()

    # 清理路径（移除外层引号）
    pdf_path = args.pdf.strip('"').strip("'").strip()
    ima_path = args.ima_path.strip('"').strip("'").strip() if args.ima_path else None

    print(f"\n解析参数:")
    print(f"  PDF路径: {pdf_path}")
    print(f"  IMA路径: {ima_path if ima_path else '未指定'}")
    print(f"  上传方法: {args.upload_method}")

    # 验证PDF路径
    if not os.path.exists(pdf_path):
        print(f"\n[ERROR] PDF文件不存在: {pdf_path}")
        sys.exit(1)

    # 创建工作流
    workflow = PDFToIMAMacro(
        pdf_path=pdf_path,
        ima_exe_path=ima_path
    )

    # 运行工作流
    success = workflow.run(upload_method=args.upload_method)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
