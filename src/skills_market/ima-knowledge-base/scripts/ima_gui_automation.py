"""
IMA客户端GUI自动化操作
使用pywinauto和pyautogui自动操作IMA客户端
"""
import os
import sys
import time
from typing import Optional

# 导入路径工具
from path_helper import CLAW_DIR, get_ima_backups_dir

# 导入config（位于scripts的父目录）
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from visible_runner import run_visible
    import config
except ImportError as e:
    print(f"导入失败: {e}")
    print(f"请确保从Claw主目录运行，或正确设置Python路径")
    print(f"Claw主目录应为: {CLAW_DIR}")
    print("请安装依赖: pip install pywinauto pyautogui")
    sys.exit(1)


class IMAGUIAutomation:
    """IMA客户端GUI自动化"""

    def __init__(self, ima_path: str = None):
        self.ima_path = ima_path or self._find_ima_exe()
        self.backup_dir = get_ima_backups_dir()
        self._ensure_backup_dir()

    def _find_ima_exe(self) -> str:
        """查找ima.exe路径"""
        paths = [
            os.environ.get('IMA_EXE_PATH'),
            r"C:\Users\qu\AppData\Local\Programs\IMA\ima.exe",
            r"C:\Program Files\IMA\ima.exe",
        ]

        for path in paths:
            if path and os.path.exists(path):
                return path

        return None

    def _ensure_backup_dir(self):
        """确保备份目录存在"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def _check_dependencies(self) -> bool:
        """检查依赖是否安装"""
        try:
            import pywinauto
            import pyautogui
            return True
        except ImportError:
            print("错误: 缺少必要的依赖")
            print("请运行: pip install pywinauto pyautogui")
            return False

    def open_ima(self, wait_time: int = 5) -> bool:
        """
        打开IMA客户端并等待

        Args:
            wait_time: 等待应用启动的秒数

        Returns:
            是否成功打开
        """
        if not self.ima_path:
            print("错误: 未找到ima.exe")
            return False

        print(f"正在打开IMA客户端: {self.ima_path}")

        try:
            # 使用弹窗方式打开
            result = run_visible(
                f'"{self.ima_path}"',
                title="IMA",
                wait=False
            )

            if result['popup_ok']:
                print(f"✓ IMA客户端已打开，等待{wait_time}秒...")
                time.sleep(wait_time)
                return True
            else:
                print(f"✗ 打开失败: {result.get('stderr', '未知错误')}")
                return False

        except Exception as e:
            print(f"✗ 打开时出错: {e}")
            return False

    def send_keystrokes(self, keys: str):
        """发送键盘按键"""
        try:
            import pyautogui
            pyautogui.press(keys)
            time.sleep(0.5)
        except ImportError:
            print("错误: pyautogui未安装")

    def type_text(self, text: str, interval: float = 0.01):
        """输入文本"""
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=interval)
            time.sleep(0.5)
        except ImportError:
            print("错误: pyautogui未安装")

    def navigate_to_knowledge_base(self):
        """导航到知识库"""
        print("导航到知识库...")
        try:
            import pyautogui

            # 通常的快捷键或点击操作
            # 这里提供通用的导航流程
            print("提示: 请手动导航到知识库界面")
            print("  - 点击左侧「知识库」或「个人知识库」")

        except ImportError:
            pass

    def export_knowledge_base(self, manual: bool = True):
        """
        导出知识库

        Args:
            manual: 是否手动操作（如果为True，显示操作提示）

        Returns:
            是否成功
        """
        print("\n" + "=" * 80)
        print("知识库导出操作")
        print("=" * 80)

        if manual:
            print("\n请在IMA客户端中执行以下操作:\n")
            print("1. 导航到个人知识库")
            print("2. 选择需要备份的文件/文件夹")
            print("3. 右键点击选中的内容")
            print("4. 选择「下载」或「导出」选项")
            print(f"5. 保存到目录: {self.backup_dir}")
            print("\n提示: 可以使用Ctrl+A全选，然后批量导出")
            print("=" * 80)

            return True

        # 自动化操作（需要根据IMA实际界面调整）
        print("\n正在尝试自动化导出...")
        print("注意: 自动化操作可能需要根据IMA版本调整")

        try:
            import pyautogui

            # 这是一个示例流程，需要根据IMA实际界面调整
            # 1. 按下快捷键（假设Ctrl+K打开知识库）
            print("按下快捷键...")
            pyautogui.hotkey('ctrl', 'k')
            time.sleep(1)

            # 2. 等待用户选择
            print("\n请在界面中:")
            print("  1. 选择要导出的文件/文件夹")
            print("  2. 按下Ctrl+C复制或右键导出")
            print("  3. 保存到: {}".format(self.backup_dir))

            input("\n按Enter键继续...")

            return True

        except Exception as e:
            print(f"\n自动化操作失败: {e}")
            print("请使用手动操作模式（默认）")
            return False

    def show_backup_info(self):
        """显示备份信息"""
        print("\n" + "=" * 80)
        print("备份信息")
        print("=" * 80)
        print(f"IMA路径: {self.ima_path}")
        print(f"备份目录: {self.backup_dir}")
        print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="IMA客户端GUI自动化")
    parser.add_argument("--ima-path", "-p", help="指定IMA客户端路径")
    parser.add_argument("--auto", "-a", action="store_true",
                       help="尝试自动化操作（需要根据IMA版本调整）")
    parser.add_argument("--open-only", "-o", action="store_true",
                       help="仅打开IMA客户端，不执行其他操作")

    args = parser.parse_args()

    # 创建自动化实例
    automation = IMAGUIAutomation(ima_path=args.ima_path)

    # 检查依赖
    if not automation._check_dependencies():
        print("\n提示: 仅使用手动操作模式")
        print("如需自动化，请安装: pip install pywinauto pyautogui")

    # 显示备份信息
    automation.show_backup_info()

    # 仅打开IMA
    if args.open_only:
        print("\n正在打开IMA客户端...")
        success = automation.open_ima(wait_time=3)

        if success:
            print("\n✓ IMA客户端已打开")
            print("请手动进行备份操作")
        else:
            print("\n✗ 打开IMA客户端失败")
            sys.exit(1)

        # 保持窗口打开
        input("\n按Enter键退出...")
        sys.exit(0)

    # 打开IMA并执行导出
    print("\n步骤1: 打开IMA客户端")
    if not automation.open_ima(wait_time=5):
        sys.exit(1)

    # 执行导出
    print("\n步骤2: 导出知识库")
    automation.export_knowledge_base(manual=not args.auto)

    print("\n操作完成！")
    input("\n按Enter键退出...")


if __name__ == "__main__":
    main()
