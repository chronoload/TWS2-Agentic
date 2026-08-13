"""
腾讯元器 (Tencent Yuanqi) API Configuration
"""
import os

# 腾讯元器API配置
# 注意：以下信息需要从腾讯元器平台获取
# 获取方式：登录 https://yuanqi.tencent.com/ → 我的创建 → 智能体 → 更多 → 调用API

YUANQI_BASE_URL = os.environ.get('YUANQI_BASE_URL', "https://yuanqi.tencent.com/api/v1/chat")
YUANQI_ASSISTANT_ID = os.environ.get('YUANQI_ASSISTANT_ID', "")  # 从平台获取
YUANQI_TOKEN = os.environ.get('YUANQI_TOKEN', "")                # 从平台获取
YUANQI_USER_ID = os.environ.get('YUANQI_USER_ID', "default_user")

# 向下兼容的配置（已弃用，建议使用上面的新配置）
IMA_BASE_URL = YUANQI_BASE_URL
IMA_API_KEY = YUANQI_TOKEN

# 本地存储目录
LOCAL_STORAGE_DIR = r"C:\Users\qu\WorkBuddy\Claw\knowledge_base_downloads"

# API请求配置
REQUEST_TIMEOUT = 30  # 请求超时时间（秒）
MAX_RETRIES = 3      # 最大重试次数
RETRY_DELAY = 2      # 重试延迟（秒）

# 下载设置
DOWNLOAD_TIMEOUT = 300  # seconds
MAX_CONCURRENT_DOWNLOADS = 5
CACHE_DURATION = 3600  # seconds (1 hour)

# 文件组织设置
ORGANIZE_BY_TYPE = True
PRESERVE_METADATA = True

# 日志
ENABLE_LOGGING = True
LOG_FILE = "yuanqi_api.log"
