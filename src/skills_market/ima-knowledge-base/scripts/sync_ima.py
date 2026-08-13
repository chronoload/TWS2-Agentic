"""
腾讯元器知识库同步脚本
定期同步知识库内容到本地存储
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import List

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

# Import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from search_ima import YuanQiChat, YuanQiError, batch_chat
except ImportError:
    print("错误: 无法导入search_ima模块")
    sys.exit(1)


class YuanQiSync:
    """腾讯元器知识库同步器"""

    def __init__(self):
        self.client = YuanQiChat()
        self.output_dir = config.LOCAL_STORAGE_DIR
        self.state_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "sync_state.json"
        )
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _load_sync_state(self) -> dict:
        """加载同步状态"""
        if not os.path.exists(self.state_file):
            return {
                "last_sync": None,
                "synced_queries": [],
                "total_queries": 0,
                "total_answers": 0
            }

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告: 加载同步状态失败: {e}")
            return {
                "last_sync": None,
                "synced_queries": [],
                "total_queries": 0,
                "total_answers": 0
            }

    def _save_sync_state(self, state: dict):
        """保存同步状态"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"警告: 保存同步状态失败: {e}")

    def _generate_sync_queries(self, topic: str, num_queries: int = 10) -> List[str]:
        """
        生成同步查询

        Args:
            topic: 主题
            num_queries: 查询数量

        Returns:
            查询列表
        """
        # 使用AI生成相关的查询
        try:
            prompt = f"""请生成 {num_queries} 个关于"{topic}"的知识库查询问题，用于同步该主题的所有相关内容。

要求：
1. 问题要覆盖该主题的不同方面
2. 问题要具体且有意义
3. 每个问题一行，不需要编号
4. 用中文提问"""

            response = self.client.chat(prompt)
            answer = self.client.extract_answer(response)

            # 解析问题列表
            questions = [line.strip() for line in answer.split('\n') if line.strip()]
            return questions[:num_queries]

        except YuanQiError:
            # 如果AI生成失败，使用预设的问题模板
            templates = [
                f"请详细介绍{topic}",
                f"{topic}的核心概念是什么",
                f"{topic}的主要特点有哪些",
                f"{topic}如何应用",
                f"{topic}的发展历程",
                f"{topic}的优势和劣势",
                f"{topic}的最佳实践",
                f"{topic}的常见问题",
                f"{topic}的最新进展",
                f"{topic}相关的重要资源"
            ]
            return templates[:num_queries]

    def sync(
        self,
        query: str,
        incremental: bool = False,
        num_queries: int = 10,
        organize_by_category: bool = False
    ) -> dict:
        """
        同步知识库内容

        Args:
            query: 查询主题
            incremental: 是否增量同步
            num_queries: 生成的问题数量
            organize_by_category: 是否按类别组织

        Returns:
            同步结果
        """
        print(f"\n{'='*80}")
        print("腾讯元器知识库同步")
        print(f"{'='*80}")
        print(f"查询主题: {query}")
        print(f"同步模式: {'增量' if incremental else '全量'}")
        print(f"输出目录: {self.output_dir}")
        print(f"{'='*80}\n")

        # 加载同步状态
        state = self._load_sync_state()

        # 增量同步：检查是否已经同步过
        if incremental and state.get("last_sync"):
            last_sync = datetime.fromisoformat(state["last_sync"])
            time_since_last = datetime.now() - last_sync

            if time_since_last < timedelta(hours=24):
                print(f"上次同步时间: {last_sync}")
                print(f"距离上次同步不足24小时，跳过增量同步")
                return {
                    "status": "skipped",
                    "reason": "最近已同步",
                    "last_sync": state["last_sync"]
                }

        # 生成查询问题
        print("正在生成同步查询...")
        queries = self._generate_sync_queries(query, num_queries)
        print(f"✓ 生成了 {len(queries)} 个查询问题\n")

        # 显示查询问题
        print("查询问题:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")
        print()

        # 批量问答
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(
            self.output_dir,
            f"sync_{timestamp}_{query[:20]}.json"
        )

        print(f"\n开始批量问答...")
        results = batch_chat(queries, output_file)

        # 按类别组织（可选）
        if organize_by_category:
            print("\n按类别组织内容...")
            self._organize_by_category(results, query)

        # 更新同步状态
        state["last_sync"] = datetime.now().isoformat()
        state["total_queries"] += len(queries)
        state["total_answers"] += sum(1 for r in results if r.get("success"))

        # 记录本次同步的查询
        if "synced_queries" not in state:
            state["synced_queries"] = []

        state["synced_queries"].append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "num_queries": len(queries),
            "num_answers": sum(1 for r in results if r.get("success")),
            "output_file": output_file
        })

        # 保存同步状态
        self._save_sync_state(state)

        # 返回结果
        return {
            "status": "success",
            "total_queries": len(queries),
            "successful_answers": sum(1 for r in results if r.get("success")),
            "failed_answers": sum(1 for r in results if not r.get("success")),
            "output_file": output_file,
            "last_sync": state["last_sync"]
        }

    def _organize_by_category(self, results: list, topic: str):
        """按类别组织结果"""
        # 创建主题目录
        safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).strip()
        topic_dir = os.path.join(self.output_dir, safe_topic)
        if not os.path.exists(topic_dir):
            os.makedirs(topic_dir)

        # 保存每个问答为独立文件
        for i, result in enumerate(results, 1):
            if result.get("success") and result.get("answer"):
                filename = os.path.join(topic_dir, f"{i:02d}_{safe_topic}.md")

                content = f"""# {result['question']}

**来源**: 腾讯元器知识库
**同步时间**: {result.get('timestamp')}
**主题**: {topic}

---

{result['answer']}

---

*本文档由腾讯元器知识库自动同步生成*
"""

                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)

        print(f"✓ 已按类别组织到: {topic_dir}")

    def show_sync_status(self):
        """显示同步状态"""
        state = self._load_sync_state()

        print(f"\n{'='*80}")
        print("同步状态")
        print(f"{'='*80}")
        print(f"上次同步: {state.get('last_sync', '从未同步')}")
        print(f"总查询数: {state.get('total_queries', 0)}")
        print(f"总回答数: {state.get('total_answers', 0)}")
        print(f"\n同步历史:")

        if state.get("synced_queries"):
            for sync in reversed(state["synced_queries"][-10:]):  # 显示最近10次
                print(f"  - {sync.get('timestamp')}: {sync.get('query')} "
                      f"({sync.get('num_answers')}/{sync.get('num_queries')})")
        else:
            print("  暂无同步记录")

        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="同步腾讯元器知识库到本地")
    parser.add_argument("--query", "-q", help="同步内容的查询主题")
    parser.add_argument("--full", action="store_true", help="全量同步")
    parser.add_argument("--incremental", "-i", action="store_true", default=True,
                       help="增量同步（仅24小时内未同步的）")
    parser.add_argument("--num-queries", "-n", type=int, default=10,
                       help="生成的查询问题数量")
    parser.add_argument("--organize", action="store_true", help="按类别组织")
    parser.add_argument("--status", "-s", action="store_true", help="显示同步状态")

    args = parser.parse_args()

    # 验证配置
    if not config.YUANQI_ASSISTANT_ID or not config.YUANQI_TOKEN:
        print("错误: 请先配置YUANQI_ASSISTANT_ID和YUANQI_TOKEN")
        print("获取方式: https://yuanqi.tencent.com/ → 我的创建 → 智能体 → 更多 → 调用API")
        sys.exit(1)

    # 创建同步器
    sync = YuanQiSync()

    # 显示状态
    if args.status:
        sync.show_sync_status()
        sys.exit(0)

    # 同步
    if not args.query:
        print("错误: 请提供 --query 或 --status")
        sys.exit(1)

    result = sync.sync(
        query=args.query,
        incremental=args.incremental and not args.full,
        num_queries=args.num_queries,
        organize_by_category=args.organize
    )

    # 显示结果
    print(f"\n{'='*80}")
    print("同步完成")
    print(f"{'='*80}")
    print(f"状态: {result['status']}")
    if result['status'] == 'success':
        print(f"总查询数: {result['total_queries']}")
        print(f"成功回答: {result['successful_answers']}")
        print(f"失败回答: {result['failed_answers']}")
        print(f"输出文件: {result['output_file']}")
        print(f"上次同步: {result['last_sync']}")
    else:
        print(f"原因: {result.get('reason', '未知')}")
    print(f"{'='*80}\n")

    sys.exit(0 if result['status'] != 'error' else 1)


if __name__ == "__main__":
    main()
