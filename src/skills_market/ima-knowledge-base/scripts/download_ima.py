"""
腾讯元器知识库内容提取脚本
从知识库中提取并保存相关文档内容
"""
import os
import sys
import json
import argparse
from datetime import datetime
from typing import List, Optional

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config
except ImportError:
    import config as config

# Import search module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from search_ima import YuanQiChat, YuanQiError
except ImportError:
    print("错误: 无法导入search_ima模块")
    sys.exit(1)


class YuanQiExtractor:
    """腾讯元器内容提取器"""

    def __init__(self):
        self.client = YuanQiChat()
        self.output_dir = config.LOCAL_STORAGE_DIR
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _generate_filename(self, topic: str, content_type: str = "md") -> str:
        """生成文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理文件名
        safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_topic = safe_topic[:50]  # 限制长度
        return f"{timestamp}_{safe_topic}.{content_type}"

    def extract_content(
        self,
        prompt: str,
        save_docs: bool = True,
        organize: bool = False,
        include_references: bool = False
    ) -> dict:
        """
        从知识库提取内容

        Args:
            prompt: 提示词，用于提取内容
            save_docs: 是否保存为文档
            organize: 是否按主题组织
            include_references: 是否包含引用

        Returns:
            提取结果字典
        """
        result = {
            "prompt": prompt,
            "content": "",
            "references": [],
            "success": False,
            "saved_files": []
        }

        try:
            # 构建提取提示词
            if include_references:
                extract_prompt = f"""请根据以下要求提取知识库中的内容，并引用相关文档：

{prompt}

请提供：
1. 详细的内容说明
2. 相关文档的引用（如有）
3. 内容的结构化组织

请用清晰的格式返回。"""
            else:
                extract_prompt = f"""请根据以下要求提取知识库中的内容：

{prompt}

请提供详细、准确的内容说明。"""

            # 调用API
            response = self.client.chat(extract_prompt)
            content = self.client.extract_answer(response)

            result["content"] = content
            result["success"] = True

            # 保存为文档
            if save_docs:
                saved_path = self._save_as_document(prompt, content, organize)
                result["saved_files"].append(saved_path)

        except YuanQiError as e:
            result["error"] = str(e)

        return result

    def _save_as_document(self, topic: str, content: str, organize: bool = False) -> str:
        """
        保存为文档

        Args:
            topic: 主题
            content: 内容
            organize: 是否组织

        Returns:
            保存的文件路径
        """
        if organize:
            # 按主题组织
            safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
            topic_dir = os.path.join(self.output_dir, safe_topic)
            if not os.path.exists(topic_dir):
                os.makedirs(topic_dir)
            filename = os.path.join(topic_dir, self._generate_filename(topic, "md"))
        else:
            filename = os.path.join(self.output_dir, self._generate_filename(topic, "md"))

        # 生成Markdown格式文档
        markdown_content = f"""# {topic}

**提取时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**来源**: 腾讯元器知识库

---

{content}

---

*本文档由腾讯元器知识库自动生成*
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        return filename

    def extract_from_chat(
        self,
        chat_history_file: str,
        extract_docs: bool = True
    ) -> dict:
        """
        从聊天历史中提取文档

        Args:
            chat_history_file: 聊天历史文件
            extract_docs: 是否提取文档

        Returns:
            提取结果
        """
        try:
            with open(chat_history_file, 'r', encoding='utf-8') as f:
                chat_history = json.load(f)

            results = {
                "chat_history": chat_history,
                "extracted_docs": []
            }

            # 分析聊天历史，提取重要信息
            for i, msg in enumerate(chat_history.get('messages', [])):
                if msg.get('role') == 'assistant':
                    content = ""
                    for c in msg.get('content', []):
                        if c.get('type') == 'text':
                            content += c.get('text', '')

                    if extract_docs and content:
                        # 保存为独立文档
                        filename = f"chat_doc_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                        filepath = os.path.join(self.output_dir, filename)

                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(f"# 聊天文档 {i}\n\n{content}")

                        results["extracted_docs"].append(filepath)

            return results

        except Exception as e:
            return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="从腾讯元器知识库提取内容")
    parser.add_argument("--query", "-q", help="提取内容的提示词")
    parser.add_argument("--chat-id", "-c", help="从聊天会话中提取")
    parser.add_argument("--save-docs", action="store_true", help="保存为文档")
    parser.add_argument("--organize", action="store_true", help="按主题组织")
    parser.add_argument("--include-references", action="store_true", help="包含引用")
    parser.add_argument("--output", "-o", help="输出目录")

    args = parser.parse_args()

    # 验证配置
    if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
        print("错误: 请先配置YUANQI_ASSISTANT_ID和YUANQI_TOKEN")
        print("获取方式: https://yuanqi.tencent.com/ → 我的创建 → 智能体 → 更多 → 调用API")
        sys.exit(1)

    # 创建提取器
    extractor = YuanQiExtractor()

    # 从聊天历史提取
    if args.chat_id:
        print(f"从聊天会话 {args.chat_id} 提取内容...")
        results = extractor.extract_from_chat(args.chat_id, args.save_docs)

        if "error" in results:
            print(f"提取失败: {results['error']}")
            sys.exit(1)

        print(f"✓ 提取完成")
        print(f"  提取的文档数量: {len(results.get('extracted_docs', []))}")
        sys.exit(0)

    # 从查询提取
    if not args.query:
        print("错误: 请提供 --query 或 --chat-id")
        sys.exit(1)

    print(f"从知识库提取内容...")
    print(f"提示词: {args.query}")
    print("=" * 80)

    result = extractor.extract_content(
        prompt=args.query,
        save_docs=args.save_docs,
        organize=args.organize,
        include_references=args.include_references
    )

    if result["success"]:
        print("✓ 内容提取成功")
        print("\n" + "=" * 80)
        print("提取的内容:")
        print("=" * 80)
        print(result["content"])
        print("=" * 80)

        if result["saved_files"]:
            print(f"\n已保存的文件:")
            for filepath in result["saved_files"]:
                print(f"  - {filepath}")
    else:
        print(f"✗ 内容提取失败: {result.get('error', '未知错误')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
