"""
腾讯元器知识库搜索脚本
向知识库提问并获取AI回答
"""
import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 导入路径工具
from path_helper import CLAW_DIR

# 导入config（位于scripts的父目录）
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import config
except ImportError:
    import config as config


class YuanQiError(Exception):
    """腾讯元器API错误"""
    pass


class YuanQiChat:
    """腾讯元器聊天/问答客户端"""

    def __init__(self):
        self.base_url = config.YUANQI_BASE_URL
        self.assistant_id = config.YUANQI_ASSISTANT_ID
        self.token = config.YUANQI_TOKEN
        self.user_id = config.YUANQI_USER_ID
        self.timeout = config.REQUEST_TIMEOUT
        self.max_retries = config.MAX_RETRIES
        self.retry_delay = config.RETRY_DELAY

        # 检查配置
        if not self.assistant_id or not self.token:
            print("警告: 请先配置YUANQI_ASSISTANT_ID和YUANQI_TOKEN")
            print("获取方式: https://yuanqi.tencent.com/ → 我的创建 → 智能体 → 更多 → 调用API")

    def _build_request(self, message: str, stream: bool = False) -> dict:
        """
        构建API请求体

        Args:
            message: 用户消息
            stream: 是否使用流式响应

        Returns:
            请求字典
        """
        return {
            "assistant_id": self.assistant_id,
            "user_id": self.user_id,
            "stream": stream,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": message
                        }
                    ]
                }
            ]
        }

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    def chat(self, message: str, stream: bool = False) -> dict:
        """
        向知识库提问（非流式）

        Args:
            message: 问题或消息
            stream: 是否使用流式响应

        Returns:
            API响应字典
        """
        request_data = self._build_request(message, stream=stream)
        headers = self._get_headers()

        for attempt in range(self.max_retries):
            try:
                print(f"正在向知识库提问 (尝试 {attempt + 1}/{self.max_retries})...")
                print(f"问题: {message}")

                response = requests.post(
                    self.base_url,
                    json=request_data,
                    headers=headers,
                    timeout=self.timeout
                )

                response.raise_for_status()
                result = response.json()

                print("✓ 回答获取成功")
                return result

            except requests.exceptions.RequestException as e:
                print(f"✗ 请求失败: {e}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay)
                else:
                    raise YuanQiError(f"API调用失败: {e}")

    def chat_stream(self, message: str):
        """
        向知识库提问（流式响应）

        Args:
            message: 问题或消息

        Yields:
            响应块
        """
        request_data = self._build_request(message, stream=True)
        headers = self._get_headers()

        try:
            print(f"正在向知识库提问（流式）...")
            print(f"问题: {message}")

            response = requests.post(
                self.base_url,
                json=request_data,
                headers=headers,
                timeout=self.timeout,
                stream=True
            )

            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    # 解析SSE格式
                    if line.startswith(b'data: '):
                        data = line[6:].decode('utf-8')
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            yield chunk
                        except json.JSONDecodeError:
                            pass

        except requests.exceptions.RequestException as e:
            raise YuanQiError(f"流式API调用失败: {e}")

    def extract_answer(self, response: dict) -> str:
        """
        从API响应中提取回答文本

        Args:
            response: API响应

        Returns:
            回答文本
        """
        try:
            messages = response.get('messages', [])
            for msg in messages:
                if msg.get('role') == 'assistant':
                    content_list = msg.get('content', [])
                    for content in content_list:
                        if content.get('type') == 'text':
                            return content.get('text', '')
            return "未找到回答"
        except Exception as e:
            return f"解析回答失败: {e}"


def display_answer(answer: str, show_json: bool = False, response_data: dict = None):
    """显示回答"""
    print("\n" + "=" * 80)
    print("知识库回答:")
    print("=" * 80)
    print(answer)
    print("=" * 80)

    if show_json and response_data:
        print("\n原始响应数据:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))


def save_answer(answer: str, filename: str, metadata: dict = None):
    """保存回答到文件"""
    try:
        data = {
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n回答已保存到: {filename}")
    except Exception as e:
        print(f"保存失败: {e}")


def batch_chat(questions: List[str], output_file: str = None) -> List[dict]:
    """
    批量问答

    Args:
        questions: 问题列表
        output_file: 输出文件路径

    Returns:
        回答列表
    """
    client = YuanQiChat()
    results = []

    print(f"\n开始批量问答，共 {len(questions)} 个问题")
    print("=" * 80)

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {question}")
        try:
            response = client.chat(question)
            answer = client.extract_answer(response)
            results.append({
                "question": question,
                "answer": answer,
                "success": True,
                "timestamp": datetime.now().isoformat()
            })
            print(f"✓ 回答已获取")
        except YuanQiError as e:
            print(f"✗ 失败: {e}")
            results.append({
                "question": question,
                "answer": "",
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

    # 保存结果
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n批量问答结果已保存到: {output_file}")

    # 统计
    success_count = sum(1 for r in results if r.get('success'))
    print(f"\n{'=' * 80}")
    print(f"批量问答完成: 成功 {success_count}/{len(questions)}")
    print(f"{'=' * 80}")

    return results


def main():
    parser = argparse.ArgumentParser(description="腾讯元器知识库问答")
    parser.add_argument("--query", "-q", help="向知识库提问")
    parser.add_argument("--query-file", "-f", help="从文件批量读取问题（每行一个问题）")
    parser.add_argument("--output", "-o", help="保存回答到文件")
    parser.add_argument("--stream", "-s", action="store_true", help="使用流式响应")
    parser.add_argument("--show-json", action="store_true", help="显示原始JSON响应")
    parser.add_argument("--batch", "-b", action="store_true", help="批量问答模式")

    args = parser.parse_args()

    # 验证配置
    if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
        print("错误: 请先配置以下参数")
        print("  - YUANQI_ASSISTANT_ID: 智能体ID")
        print("  - YUANQI_TOKEN: API令牌")
        print("\n获取方式:")
        print("  1. 访问 https://yuanqi.tencent.com/")
        print("  2. 点击「我的创建」")
        print("  3. 找到你的智能体，点击「更多」→「调用API」")
        print("  4. 复制 assistant_id 和 token 到 config.py 或设置环境变量")
        sys.exit(1)

    # 批量问答模式
    if args.query_file:
        try:
            with open(args.query_file, 'r', encoding='utf-8') as f:
                questions = [line.strip() for line in f if line.strip()]
            if not questions:
                print("错误: 文件中没有问题")
                sys.exit(1)
            batch_chat(questions, args.output)
            sys.exit(0)
        except Exception as e:
            print(f"读取问题文件失败: {e}")
            sys.exit(1)

    # 单个问答
    if not args.query:
        print("错误: 请提供 --query 或 --query-file")
        sys.exit(1)

    # 创建客户端
    client = YuanQiChat()

    # 流式响应
    if args.stream:
        try:
            print("\n流式回答:")
            for chunk in client.chat_stream(args.query):
                # 尝试提取文本
                if 'choices' in chunk and len(chunk['choices']) > 0:
                    delta = chunk['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    print(content, end='', flush=True)
                elif 'messages' in chunk:
                    # 另一种响应格式
                    for msg in chunk['messages']:
                        if msg.get('role') == 'assistant':
                            for content in msg.get('content', []):
                                if content.get('type') == 'text':
                                    print(content.get('text', ''), end='', flush=True)
            print()  # 换行
        except YuanQiError as e:
            print(f"流式问答失败: {e}")
            sys.exit(1)
    else:
        # 非流式响应
        try:
            response = client.chat(args.query)
            answer = client.extract_answer(response)
            display_answer(answer, show_json=args.show_json, response_data=response)

            # 保存回答
            if args.output:
                metadata = {
                    "query": args.query,
                    "assistant_id": config.YUANQI_ASSISTANT_ID,
                    "response": response
                }
                save_answer(answer, args.output, metadata)

        except YuanQiError as e:
            print(f"问答失败: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
