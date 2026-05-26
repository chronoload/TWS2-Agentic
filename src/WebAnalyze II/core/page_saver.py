"""
页面保存器 - 基于 webscrapy 思路的页面保存系统
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import logging


class PageSaver:
    """
    页面保存器
    支持保存HTML页面、构建索引、管理历史记录
    """

    def __init__(self, base_dir: str = "./data/pages"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # 创建子目录
        self.html_dir = self.base_dir / "html"
        self.html_dir.mkdir(exist_ok=True)
        
        self.css_dir = self.base_dir / "css"
        self.css_dir.mkdir(exist_ok=True)
        
        self.js_dir = self.base_dir / "js"
        self.js_dir.mkdir(exist_ok=True)
        
        self.images_dir = self.base_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        
        # 索引文件
        self.index_file = self.base_dir / "pages_index.json"
        self.index = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        """加载页面索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加载索引失败: {e}")
                return {}
        return {}

    def _save_index(self):
        """保存页面索引"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def save_page(self, url: str, html: str, metadata: Dict[str, Any] = None) -> str:
        """
        保存页面
        
        Args:
            url: 页面URL
            html: HTML内容
            metadata: 元数据
            
        Returns:
            保存的文件路径
        """
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = self._generate_filename(url, timestamp)
        filepath = self.html_dir / filename
        
        # 保存HTML
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # 更新索引
        self.index[url] = {
            'filename': filename,
            'filepath': str(filepath),
            'url': url,
            'saved_time': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        self._save_index()
        self.logger.info(f"页面已保存: {filepath}")
        
        return str(filepath)

    def _generate_filename(self, url: str, timestamp: str) -> str:
        """生成文件名"""
        # 从URL提取文件名
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        if path:
            # 替换特殊字符
            safe_path = ''.join(c if c.isalnum() else '_' for c in path)
            return f"{safe_path}_{timestamp}.html"
        else:
            return f"page_{timestamp}.html"

    def get_page(self, url: str) -> str:
        """获取保存的页面内容"""
        if url in self.index:
            filepath = self.index[url]['filepath']
            if Path(filepath).exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
        return None

    def get_all_pages(self) -> List[Dict[str, Any]]:
        """获取所有页面信息"""
        return list(self.index.values())

    def export_index(self, export_path: str):
        """导出索引"""
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
            self.logger.info(f"索引已导出到: {export_path}")
        except Exception as e:
            self.logger.error(f"导出索引失败: {e}")

    def clear_old_pages(self, days: int = 30):
        """清理旧页面"""
        import time
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        removed = 0
        
        for url, info in list(self.index.items()):
            saved_time = datetime.fromisoformat(info['saved_time'])
            if saved_time < cutoff_date:
                # 删除文件
                filepath = Path(info['filepath'])
                if filepath.exists():
                    filepath.unlink()
                
                # 从索引中删除
                del self.index[url]
                removed += 1
        
        if removed > 0:
            self._save_index()
            self.logger.info(f"清理了 {removed} 个旧页面")