"""Simple test without unicode symbols"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config
    print("[OK] Config loaded")
    print(f"YUANQI_BASE_URL: {config.YUANQI_BASE_URL}")
    print(f"YUANQI_ASSISTANT_ID: {config.YUANQI_ASSISTANT_ID if config.YUANQI_ASSISTANT_ID else 'Not configured'}")
    print(f"YUANQI_TOKEN: {config.YUANQI_TOKEN if config.YUANQI_TOKEN else 'Not configured'}")
    print(f"LOCAL_STORAGE_DIR: {config.LOCAL_STORAGE_DIR}")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

try:
    from search_ima import YuanQiChat
    print("[OK] search_ima module imported")
except Exception as e:
    print(f"[ERROR] search_ima: {e}")

try:
    from download_ima import YuanQiExtractor
    print("[OK] download_ima module imported")
except Exception as e:
    print(f"[ERROR] download_ima: {e}")

try:
    from sync_ima import YuanQiSync
    print("[OK] sync_ima module imported")
except Exception as e:
    print(f"[ERROR] sync_ima: {e}")

print("\n[SUCCESS] All tests completed")
