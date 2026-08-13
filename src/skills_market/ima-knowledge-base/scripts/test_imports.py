"""
测试IMA skill的所有导入
验证项目结构和依赖是否正确配置
"""
import sys
import os

# Windows 控制台编码处理
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("=" * 80)
print("IMA Skill 导入测试")
print("=" * 80)
print()

# 测试1: 导入path_helper
print("测试1: 导入 path_helper...")
try:
    from path_helper import CLAW_DIR, get_logs_dir, get_ima_backups_dir
    print("[OK] path_helper 导入成功")
    print(f"  Claw目录: {CLAW_DIR}")
    print(f"  日志目录: {get_logs_dir()}")
    print(f"  备份目录: {get_ima_backups_dir()}")
    print()
except ImportError as e:
    print(f"[FAIL] path_helper 导入失败: {e}")
    sys.exit(1)

# 测试2: 导入visible_runner
print("测试2: 导入 visible_runner...")
try:
    from visible_runner import run_visible
    print("[OK] visible_runner 导入成功")
    print(f"  函数: run_visible")
    print()
except ImportError as e:
    print(f"[FAIL] visible_runner 导入失败: {e}")
    print(f"  请确保 visible_runner.py 在 Claw 主目录中")
    sys.exit(1)

# 测试3: 导入config
print("测试3: 导入 config...")
try:
    import config
    print("[OK] config 导入成功")
    print(f"  YuanQi Base URL: {config.YUANQI_BASE_URL}")
    print(f"  Assistant ID: {config.YUANQI_ASSISTANT_ID or '未配置'}")
    print(f"  Token: {'已配置' if config.YUANQI_TOKEN else '未配置'}")
    print()
except ImportError as e:
    print(f"[FAIL] config 导入失败: {e}")
    sys.exit(1)

# 测试4: 导入search_ima
print("测试4: 导入 search_ima...")
try:
    from search_ima import YuanQiChat, YuanQiError
    print("[OK] search_ima 导入成功")
    print(f"  类: YuanQiChat")
    print(f"  异常: YuanQiError")
    print()
except ImportError as e:
    print(f"[FAIL] search_ima 导入失败: {e}")
    sys.exit(1)

# 测试5: 导入backup_to_ima模块
print("测试5: 导入 backup_to_ima 模块...")
try:
    from backup_to_ima import IMABackupWorkflow
    print("[OK] backup_to_ima 导入成功")
    print(f"  类: IMABackupWorkflow")
    print()
except ImportError as e:
    print(f"[FAIL] backup_to_ima 导入失败: {e}")
    sys.exit(1)

# 测试6: 导入ima_gui_automation模块
print("测试6: 导入 ima_gui_automation 模块...")
try:
    from ima_gui_automation import IMAGUIAutomation
    print("[OK] ima_gui_automation 导入成功")
    print(f"  类: IMAGUIAutomation")
    print()
except ImportError as e:
    print(f"[FAIL] ima_gui_automation 导入失败: {e}")
    sys.exit(1)

# 测试7: 导入sync_ima模块
print("测试7: 导入 sync_ima 模块...")
try:
    from sync_ima import YuanQiSync
    print("[OK] sync_ima 导入成功")
    print(f"  类: YuanQiSync")
    print()
except ImportError as e:
    print(f"[FAIL] sync_ima 导入失败: {e}")
    sys.exit(1)

print("=" * 80)
print("[OK] 所有导入测试通过！")
print("=" * 80)
print()
print("项目结构检查:")
print(f"  [OK] Claw主目录: {CLAW_DIR}")
print(f"  [OK] path_helper正确")
print(f"  [OK] visible_runner可导入")
print(f"  [OK] config可导入")
print(f"  [OK] 所有IMA skill模块可导入")
print()
print("可以开始使用IMA skill了！")
