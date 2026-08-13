"""
PDF到IMA知识库快速开始示例

使用方法：
1. 修改下面的配置参数
2. 运行此脚本：python pdf_to_ima_quickstart.py
"""
import sys
import os

# 添加路径
current_file = os.path.abspath(__file__)
claw_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
scripts_dir = os.path.join(claw_root, '.codebuddy', 'skills', 'ima-knowledge-base', 'scripts')

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from pdf_to_ima_final import PDFToIMAWorkflow

# ==================== 配置区域 ====================

# 1. PDF文件路径（必填）
PDF_PATH = r"C:\Users\qu\Desktop\高等代数 第五版 (北大数学系前线代小组 王萼芳 石生明) (Z-Library)_有目录.pdf"

# 2. IMA客户端路径（可选，不填则不自动启动）
IMA_PATH = r"F:\ima.copilot\ima.copilot.exe"

# 3. 文档标签（可选）
TAGS = ["PDF", "文档", "数学", "高等代数", "教材"]

# 4. 文档描述（可选）
DESCRIPTION = "高等代数教科书 - 第五版 - 北大数学系"

# ==================== 执行区域 ====================

def main():
    print("=" * 80)
    print("PDF到IMA知识库快速开始")
    print("=" * 80)

    # 验证配置
    if not os.path.exists(PDF_PATH):
        print(f"\n[ERROR] PDF文件不存在: {PDF_PATH}")
        print("\n请修改脚本中的PDF_PATH参数")
        input("\n按Enter键退出...")
        return False

    print(f"\n配置信息:")
    print(f"  PDF路径: {PDF_PATH}")
    print(f"  IMA路径: {IMA_PATH or '未配置'}")
    print(f"  标签: {', '.join(TAGS)}")
    print(f"  描述: {DESCRIPTION}")

    # 创建工作流
    workflow = PDFToIMAWorkflow(
        pdf_path=PDF_PATH,
        ima_exe_path=IMA_PATH
    )

    # 运行工作流
    print("\n开始处理...")
    success = workflow.run()

    if success:
        print("\n" + "=" * 80)
        print("[OK] 处理完成！")
        print("=" * 80)
        print("\n下一步：")
        print("  1. 查看上传指南了解详细步骤")
        print("  2. 在IMA客户端中按照指南上传文档")
        print("  3. 验证上传成功")
    else:
        print("\n[ERROR] 处理失败，请检查日志")

    input("\n按Enter键退出...")
    return success


if __name__ == "__main__":
    main()
