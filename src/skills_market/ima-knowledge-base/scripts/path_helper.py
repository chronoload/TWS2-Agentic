"""
Claw路径工具
用于统一管理Python路径，确保所有子模块都能正确导入主目录的工具
"""
import os
import sys

# 获取Claw主目录
# scripts目录的路径：Claw/.codebuddy/skills/ima-knowledge-base/scripts/
# 需要向上5级到达Claw主目录
# scripts -> ima-knowledge-base -> skills -> .codebuddy -> Claw
current_file = os.path.abspath(__file__)
CLAW_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file)))))

# 确保Claw主目录在sys.path中
if CLAW_DIR not in sys.path:
    sys.path.insert(0, CLAW_DIR)

def get_claw_dir() -> str:
    """获取Claw主目录路径"""
    return CLAW_DIR

def get_logs_dir() -> str:
    """获取日志目录路径"""
    return os.path.join(CLAW_DIR, "logs")

def get_ima_backups_dir() -> str:
    """获取IMA备份目录路径"""
    return os.path.join(CLAW_DIR, "ima_backups")

# 确保必要的目录存在
os.makedirs(get_logs_dir(), exist_ok=True)
os.makedirs(get_ima_backups_dir(), exist_ok=True)
