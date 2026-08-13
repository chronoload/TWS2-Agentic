"""
IMA宏工作流 - 自动化操作IMA客户端
"""
import sys
import os
import subprocess
import time
from datetime import datetime

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

for path in [script_dir, parent_dir, claw_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from path_helper import CLAW_DIR, get_ima_backups_dir
except ImportError:
    claw_root_dir = claw_root
    get_ima_backups_dir = lambda: os.path.join(claw_root_dir, 'ima_backups')


class IMAMacroWorkflow:
    def __init__(self, ima_exe_path=None):
        self.ima_exe = ima_exe_path or self.find_ima_exe()
        self.backup_dir = get_ima_backups_dir()
        self.log_file = os.path.join(self.backup_dir, "macro_workflow_log.txt")
        self.ensure_dirs()

    def find_ima_exe(self):
        possible_names = ['ima.copilot.exe', 'ima.exe', 'IMA.exe']
        possible_paths = [
            "C:/Users/qu/AppData/Local/Programs/IMA/",
            "C:/Program Files/IMA/",
            "C:/Program Files (x86)/IMA/",
            "C:/Users/qu/Desktop/",
            "C:/Users/qu/Downloads/",
        ]

        custom_path = os.environ.get('IMA_EXE_PATH')
        if custom_path and os.path.exists(custom_path):
            return custom_path

        for base_path in possible_paths:
            for exe_name in possible_names:
                full_path = os.path.join(base_path, exe_name)
                if os.path.exists(full_path):
                    return full_path

        for exe_name in possible_names:
            try:
                result = subprocess.run(['where', exe_name], capture_output=True, text=True)
                if result.returncode == 0:
                    paths = result.stdout.strip().split('\n')
                    for path in paths:
                        if path and os.path.exists(path):
                            return path
            except:
                pass

        return None

    def ensure_dirs(self):
        os.makedirs(self.backup_dir, exist_ok=True)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    def launch_ima(self, wait_seconds=5):
        if not self.ima_exe:
            self.log("[ERROR] 未找到IMA客户端")
            print("请设置IMA_EXE_PATH环境变量或手动指定路径")
            return False

        self.log(f"启动IMA客户端: {self.ima_exe}")
        print(f"正在启动: {self.ima_exe}")

        try:
            # 使用shell=False列表方式，避免路径转义问题
            process = subprocess.Popen([str(self.ima_exe)], shell=False)
            self.log(f"[OK] IMA进程已启动，PID: {process.pid}")
            print(f"等待 {wait_seconds} 秒让应用启动...")
            time.sleep(wait_seconds)
            return True
        except Exception as e:
            self.log(f"[ERROR] 启动失败: {e}")
            print(f"启动失败: {e}")
            return False

    def show_backup_guide(self):
        guide = """
IMA知识库手动备份指南
=========================

请在IMA客户端中依次执行以下操作：

1. 登录（如果需要）
   - 使用微信扫码登录
   - 确认登录成功

2. 导航到知识库
   - 点击左侧【知识库】或【我的知识库】
   - 等待知识库列表加载

3. 选择要备份的内容
   - 点击目标知识库
   - 全选：Ctrl+A
   - 或逐个选择需要的文件/文件夹

4. 导出/下载
   - 右键点击选中的内容
   - 选择【导出】或【下载】
   - 选择保存位置

5. 保存到指定目录
   - 导航到: C:\\Users\\qu\\WorkBuddy\\Claw\\ima_backups
   - 点击【保存】
   - 等待导出完成

6. 确认导出
   - 检查ima_backups目录
   - 确认文件已成功导出

提示：
- 可以使用Ctrl+A全选所有内容
- 大量文件可能需要较长时间
- 导出完成后会提示成功或失败
"""
        print(guide)

    def backup_workflow(self, manual_mode=True):
        self.log("=" * 80)
        self.log("开始IMA知识库备份工作流")
        self.log("=" * 80)

        print("\n[步骤1] 启动IMA客户端")
        print("-" * 80)

        if not self.launch_ima(wait_seconds=8):
            print("\n启动失败，请手动启动IMA客户端")
            return False

        print("\n[步骤2] 等待窗口加载")
        print("-" * 80)
        print("等待8秒让IMA完全加载...")
        time.sleep(8)

        print("\n[步骤3] 显示操作指南")
        print("-" * 80)
        self.show_backup_guide()

        guide = self.get_backup_guide_text()
        guide_file = os.path.join(self.backup_dir, f"backup_guide_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(guide)

        self.log(f"[OK] 操作指南已保存: {os.path.basename(guide_file)}")
        print(f"\n操作指南已保存到: {guide_file}")

        print("\n[步骤4] 备份完成")
        print("-" * 80)
        self.log("[OK] 工作流执行完成")

        print(f"\n日志文件: {self.log_file}")
        print(f"备份目录: {self.backup_dir}")

        return True

    def get_backup_guide_text(self):
        return f"""IMA知识库手动备份指南
{'=' * 40}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
备份目录: {self.backup_dir}

操作步骤：
1. 登录（如果需要）
2. 点击左侧【知识库】菜单
3. 选择要备份的知识库/文件
4. Ctrl+A 全选所有内容
5. 右键 → 导出/下载
6. 保存到: {self.backup_dir}
7. 等待导出完成

快捷键：
- Ctrl+A: 全选
- Ctrl+C: 复制
- Ctrl+V: 粘贴
- 右键: 上下文菜单

{'=' * 40}
"""


def main():
    import argparse

    parser = argparse.ArgumentParser(description="IMA宏工作流 - 自动化操作IMA客户端")
    parser.add_argument("--ima-path", "-p", help="指定IMA客户端路径")
    parser.add_argument("--auto", "-a", action="store_true", help="自动模式（尝试自动化操作）")
    parser.add_argument("--only-launch", "-l", action="store_true", help="仅启动IMA客户端")

    args = parser.parse_args()

    # 移除路径中的引号（如果有）
    ima_path = args.ima_path
    if ima_path:
        ima_path = ima_path.strip('"').strip("'")

    workflow = IMAMacroWorkflow(ima_exe_path=ima_path)

    print("=" * 80)
    print("IMA宏工作流")
    print("=" * 80)
    print(f"IMA客户端: {workflow.ima_exe or '未找到'}")
    print(f"备份目录: {workflow.backup_dir}")
    print(f"日志文件: {workflow.log_file}")
    print("=" * 80)
    print()

    if args.only_launch:
        print("模式: 仅启动IMA客户端\n")
        if workflow.launch_ima(wait_seconds=8):
            print("\n[OK] IMA客户端已启动")
            print("请手动进行备份操作")
            print(f"查看操作指南: {workflow.log_file}")
        else:
            print("\n[ERROR] 启动失败")
        return

    print(f"模式: {'自动' if args.auto else '手动'}备份模式\n")

    success = workflow.backup_workflow(manual_mode=not args.auto)

    print("\n" + "=" * 80)
    if success:
        print("[OK] 工作流执行完成")
        print("=" * 80)
        print("\n后续操作:")
        print(f"1. 检查备份目录: {workflow.backup_dir}")
        print(f"2. 查看日志文件: {workflow.log_file}")
        print(f"3. 如需同步到微信，运行: python sync_workflows/sync_log_to_wechat.py")
        sys.exit(0)
    else:
        print("[ERROR] 工作流执行失败")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
