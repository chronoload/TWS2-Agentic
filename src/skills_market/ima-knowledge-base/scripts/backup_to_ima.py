"""
IMA知识库备份工作流
当腾讯元器不可用时，打开本地IMA客户端进行备份操作
"""
import os
import sys
import json
import time
from datetime import datetime

# Windows控制台编码处理
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 导入路径工具
from path_helper import CLAW_DIR, get_ima_backups_dir

# 导入config（位于scripts的父目录）
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from visible_runner import run_visible
    from search_ima import YuanQiChat, YuanQiError
    import config
except ImportError as e:
    print(f"导入失败: {e}")
    print(f"请确保从Claw主目录运行，或正确设置Python路径")
    print(f"Claw主目录应为: {CLAW_DIR}")
    sys.exit(1)


class IMABackupWorkflow:
    """IMA知识库备份工作流"""

    def __init__(self):
        self.ima_exe_path = self._find_ima_exe()
        self.backup_dir = get_ima_backups_dir()
        self.log_file = os.path.join(self.backup_dir, "backup_log.json")
        self._ensure_backup_dir()

    def _find_ima_exe(self) -> str:
        """查找ima.exe路径"""
        # 常见的IMA安装路径
        possible_paths = [
            r"C:\Users\qu\AppData\Local\Programs\IMA\ima.exe",
            r"C:\Program Files\IMA\ima.exe",
            r"C:\Program Files (x86)\IMA\ima.exe",
            r"C:\Users\qu\Desktop\ima.exe",
            r"C:\Users\qu\Downloads\ima.exe",
        ]

        # 用户自定义路径
        custom_path = os.environ.get('IMA_EXE_PATH')
        if custom_path and os.path.exists(custom_path):
            return custom_path

        # 搜索常见路径
        for path in possible_paths:
            if os.path.exists(path):
                return path

        # 如果都找不到，尝试使用where命令
        try:
            result = os.popen('where ima.exe').read()
            if result:
                return result.strip().split('\n')[0]
        except:
            pass

        return None

    def _ensure_backup_dir(self):
        """确保备份目录存在"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def _load_backup_log(self) -> dict:
        """加载备份日志"""
        if not os.path.exists(self.log_file):
            return {"backups": []}

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"backups": []}

    def _save_backup_log(self, log: dict):
        """保存备份日志"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存备份日志失败: {e}")

    def _test_yuanqi_connection(self) -> bool:
        """测试腾讯元器连接"""
        try:
            if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
                return False

            client = YuanQiChat()
            # 发送一个简单的测试请求
            response = client.chat("测试连接")
            return bool(response)
        except YuanQiError:
            return False
        except Exception:
            return False

    def open_ima_client(self) -> bool:
        """打开IMA客户端"""
        if not self.ima_exe_path:
            print("错误: 未找到ima.exe")
            print("请设置环境变量 IMA_EXE_PATH 或手动指定路径")
            return False

        print(f"正在打开IMA客户端: {self.ima_exe_path}")
        print("=" * 80)

        try:
            # 使用弹窗方式打开IMA客户端
            result = run_visible(
                f'"{self.ima_exe_path}"',
                title="IMA知识库客户端",
                wait=False  # 不等待关闭
            )

            if result['popup_ok']:
                print("[OK] IMA客户端已打开")
                print("\n请在IMA客户端中进行以下操作:")
                print("  1. 登录（如果需要）")
                print("  2. 打开个人知识库")
                print("  3. 选择需要备份的文件/文件夹")
                print("  4. 右键 → 下载/导出到本地")
                print("  5. 保存到备份目录:")
                print(f"     {self.backup_dir}")
                print("\n操作完成后，按任意键关闭此窗口...")
                return True
            else:
                print(f"[FAIL] 打开IMA客户端失败: {result.get('stderr', '未知错误')}")
                return False

        except Exception as e:
            print(f"[FAIL] 打开IMA客户端时出错: {e}")
            return False

    def run_backup_workflow(self, force_ima: bool = False) -> dict:
        """
        运行备份工作流

        Args:
            force_ima: 强制使用IMA客户端

        Returns:
            备份结果字典
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "mode": None,
            "success": False,
            "error": None
        }

        print("=" * 80)
        print("IMA知识库备份工作流")
        print("=" * 80)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"备份目录: {self.backup_dir}")
        print("=" * 80)
        print()

        # 1. 检查腾讯元器连接
        if not force_ima:
            print("步骤1: 检查腾讯元器连接...")
            yuanqi_available = self._test_yuanqi_connection()

            if yuanqi_available:
                print("[OK] 腾讯元器连接正常")
                print("\n建议使用腾讯元器API进行备份（功能更完整）")
                print("如需使用IMA客户端，请使用 --force-ima 参数")
                result["mode"] = "yuanqi_available"
                result["success"] = True
                return result
            else:
                print("[FAIL] 腾讯元器不可用")
                print("   原因: 未配置API凭证或连接失败")
                print()
        else:
            print("步骤1: 强制使用IMA客户端（跳过元器检查）\n")

        # 2. 打开IMA客户端
        print("步骤2: 打开IMA客户端进行备份...")

        if self.ima_exe_path:
            print(f"[OK] 找到IMA客户端: {self.ima_exe_path}")
        else:
            print("[WARN] 未找到IMA客户端，尝试使用默认路径")
            print("   常见安装位置:")
            print("   - C:\\Users\\qu\\AppData\\Local\\Programs\\IMA\\ima.exe")
            print("   - C:\\Program Files\\IMA\\ima.exe")
            print()
            response = input("请输入IMA客户端的完整路径，或按Enter继续: ").strip()

            if response:
                if os.path.exists(response):
                    self.ima_exe_path = response
                else:
                    result["error"] = f"路径不存在: {response}"
                    return result
            else:
                result["error"] = "未提供IMA客户端路径"
                return result

        # 3. 执行打开操作
        success = self.open_ima_client()

        if success:
            result["mode"] = "ima_client"
            result["success"] = True

            # 记录备份日志
            log = self._load_backup_log()
            log["backups"].append({
                "timestamp": result["timestamp"],
                "mode": "ima_client",
                "ima_path": self.ima_exe_path,
                "backup_dir": self.backup_dir
            })
            self._save_backup_log(log)

        else:
            result["error"] = "打开IMA客户端失败"

        return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="IMA知识库备份工作流")
    parser.add_argument("--force-ima", "-f", action="store_true",
                       help="强制使用IMA客户端（跳过元器检查）")
    parser.add_argument("--ima-path", "-p", help="指定IMA客户端路径")
    parser.add_argument("--test-connection", "-t", action="store_true",
                       help="仅测试腾讯元器连接")

    args = parser.parse_args()

    # 仅测试连接
    if args.test_connection:
        print("测试腾讯元器连接...")
        workflow = IMABackupWorkflow()
        if workflow._test_yuanqi_connection():
            print("[OK] 连接成功")
            sys.exit(0)
        else:
            print("[FAIL] 连接失败")
            print("  请检查config.py中的YUANQI_ASSISTANT_ID和YUANQI_TOKEN")
            sys.exit(1)

    # 创建工作流
    workflow = IMABackupWorkflow()

    # 设置自定义IMA路径
    if args.ima_path:
        if os.path.exists(args.ima_path):
            workflow.ima_exe_path = args.ima_path
        else:
            print(f"错误: 路径不存在: {args.ima_path}")
            sys.exit(1)

    # 运行备份工作流
    result = workflow.run_backup_workflow(force_ima=args.force_ima)

    # 显示结果
    print("\n" + "=" * 80)
    print("备份工作流完成")
    print("=" * 80)
    print(f"模式: {result['mode']}")
    print(f"状态: {'[OK] 成功' if result['success'] else '[FAIL] 失败'}")

    if result.get('error'):
        print(f"错误: {result['error']}")

    print("=" * 80)

    sys.exit(0 if result['success'] else 1)


if __name__ == "__main__":
    main()
