"""
IMA知识库快速备份
一键启动备份工作流
"""
import os
import sys

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def quick_backup():
    """快速备份入口"""
    print("=" * 80)
    print("IMA知识库快速备份")
    print("=" * 80)
    print()

    # 检查IMA路径
    ima_path = os.environ.get('IMA_EXE_PATH')
    if ima_path and os.path.exists(ima_path):
        print(f"✓ 找到IMA客户端: {ima_path}")
    else:
        print("⚠ 未配置IMA客户端路径")
        print("  请设置环境变量 IMA_EXE_PATH")
        print("  示例: C:\\Users\\qu\\AppData\\Local\\Programs\\IMA\\ima.exe")
        print()

    # 选择模式
    print("请选择备份模式:")
    print("  1. 自动检测（推荐）")
    print("     - 先尝试腾讯元器API")
    print("     - 不可用时打开IMA客户端")
    print()
    print("  2. 强制使用IMA客户端")
    print("     - 跳过元器检测，直接打开IMA")
    print()
    print("  3. 仅打开IMA客户端")
    print("     - 不执行备份，只打开应用")
    print()

    choice = input("请输入选项 (1-3，默认1): ").strip() or "1"

    print()

    # 执行相应操作
    if choice == "1":
        # 自动检测模式
        print("模式: 自动检测")
        os.system(f'python "{os.path.dirname(__file__)}/backup_to_ima.py"')

    elif choice == "2":
        # 强制使用IMA
        print("模式: 强制使用IMA客户端")
        os.system(f'python "{os.path.dirname(__file__)}/backup_to_ima.py" --force-ima')

    elif choice == "3":
        # 仅打开IMA
        print("模式: 仅打开IMA客户端")
        os.system(f'python "{os.path.dirname(__file__)}/ima_gui_automation.py" --open-only')

    else:
        print("无效选项")
        sys.exit(1)


if __name__ == "__main__":
    try:
        quick_backup()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
