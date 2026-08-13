"""macdev.exe 打包入口：python -m 语义转换为绝对导入（pyinstaller 以脚本方式运行）。"""
from macdev.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
