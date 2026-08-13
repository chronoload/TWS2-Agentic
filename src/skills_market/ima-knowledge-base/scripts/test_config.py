"""
测试配置和基本功能（无需实际API调用）
"""
import os
import sys
import io

# 设置标准输出为UTF-8编码（解决Windows命令行编码问题）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_config():
    """测试配置文件"""
    print("=" * 80)
    print("配置文件测试")
    print("=" * 80)

    try:
        import config

        # 检查基本配置
        print(f"\n✓ 配置文件加载成功")

        # 检查API配置
        print(f"\nAPI配置:")
        print(f"  YUANQI_BASE_URL: {config.YUANQI_BASE_URL}")
        print(f"  YUANQI_ASSISTANT_ID: {'已配置' if config.YUANQI_ASSISTANT_ID else '未配置'}")
        print(f"  YUANQI_TOKEN: {'已配置' if config.YUANQI_TOKEN else '未配置'}")
        print(f"  YUANQI_USER_ID: {config.YUANQI_USER_ID}")

        # 检查其他配置
        print(f"\n其他配置:")
        print(f"  LOCAL_STORAGE_DIR: {config.LOCAL_STORAGE_DIR}")
        print(f"  REQUEST_TIMEOUT: {config.REQUEST_TIMEOUT}s")
        print(f"  MAX_RETRIES: {config.MAX_RETRIES}")

        # 验证配置
        if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
            print(f"\n⚠ 警告: API凭证未配置")
            print(f"请从以下地址获取:")
            print(f"  https://yuanqi.tencent.com/")
            print(f"  我的创建 → 智能体 → 更多 → 调用API")
            return False
        else:
            print(f"\n✓ 配置完整，可以正常使用")
            return True

    except Exception as e:
        print(f"\n✗ 配置文件错误: {e}")
        return False


def test_imports():
    """测试模块导入"""
    print("\n" + "=" * 80)
    print("模块导入测试")
    print("=" * 80)

    try:
        from search_ima import YuanQiChat, YuanQiError
        print("✓ search_ima 模块导入成功")
    except Exception as e:
        print(f"✗ search_ima 模块导入失败: {e}")
        return False

    try:
        from download_ima import YuanQiExtractor
        print("✓ download_ima 模块导入成功")
    except Exception as e:
        print(f"✗ download_ima 模块导入失败: {e}")
        return False

    try:
        from sync_ima import YuanQiSync
        print("✓ sync_ima 模块导入成功")
    except Exception as e:
        print(f"✗ sync_ima 模块导入失败: {e}")
        return False

    return True


def test_output_dir():
    """测试输出目录"""
    print("\n" + "=" * 80)
    print("输出目录测试")
    print("=" * 80)

    try:
        import config
        output_dir = config.LOCAL_STORAGE_DIR

        if not os.path.exists(output_dir):
            print(f"创建输出目录: {output_dir}")
            os.makedirs(output_dir, exist_ok=True)

        if os.path.exists(output_dir):
            print(f"✓ 输出目录存在: {output_dir}")
            print(f"  可写: {os.access(output_dir, os.W_OK)}")
            return True
        else:
            print(f"✗ 无法创建输出目录: {output_dir}")
            return False

    except Exception as e:
        print(f"✗ 输出目录测试失败: {e}")
        return False


def main():
    print("\n腾讯元器知识库技能 - 功能测试\n")

    results = {
        "配置测试": test_config(),
        "模块测试": test_imports(),
        "目录测试": test_output_dir()
    }

    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    for test_name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print(f"\n整体状态: {'✓ 所有测试通过' if all_passed else '✗ 部分测试失败'}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
