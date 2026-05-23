"""
实时调试工具 - 提供爬虫运行时监控和调试功能
"""
import json
import queue
import threading
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional
from collections import deque
from dataclasses import dataclass, asdict
import time


@dataclass
class DebugEvent:
    """调试事件"""
    timestamp: str
    level: str  # 'debug', 'info', 'warning', 'error', 'success'
    component: str  # 'crawler', 'parser', 'network', 'storage' 等
    message: str
    data: Optional[Dict] = None

    def to_dict(self):
        return asdict(self)


class RealTimeDebugger:
    """实时调试器 - 用于监控和调试爬虫运行"""

    def __init__(self, max_events=1000, enable_network_log=True):
        """
        初始化调试器
        
        Args:
            max_events: 最大缓存事件数
            enable_network_log: 是否启用网络日志
        """
        self.max_events = max_events
        self.enable_network_log = enable_network_log
        
        # 事件队列和日志
        self.event_queue = queue.Queue()
        self.events = deque(maxlen=max_events)
        self.network_logs = deque(maxlen=max_events)
        
        # 统计数据
        self.stats = {
            'total_requests': 0,
            'total_responses': 0,
            'total_errors': 0,
            'total_bytes': 0,
            'start_time': datetime.now().isoformat(),
            'urls_visited': set(),
            'error_counts': {}
        }
        
        # 回调函数
        self.callbacks: Dict[str, List[Callable]] = {
            'on_event': [],
            'on_error': [],
            'on_network_request': [],
            'on_network_response': [],
            'on_performance_alert': []
        }
        
        # 性能阈值
        self.performance_thresholds = {
            'slow_page': 5000,  # 5秒
            'slow_request': 10000,  # 10秒
            'large_response': 10 * 1024 * 1024  # 10MB
        }
        
        # 启动事件处理线程
        self.running = True
        self.event_thread = threading.Thread(target=self._process_events, daemon=True)
        self.event_thread.start()

    def log_event(self, level: str, component: str, message: str, data: Optional[Dict] = None):
        """
        记录事件
        
        Args:
            level: 日志级别 (debug, info, warning, error, success)
            component: 组件名称
            message: 消息内容
            data: 附加数据
        """
        # 简单清理 data，避免记录过大的 HTML 或长字符串
        sanitized = self._sanitize_data(data)
        event = DebugEvent(
            timestamp=datetime.now().isoformat(),
            level=level,
            component=component,
            message=message,
            data=sanitized
        )
        
        self.events.append(event)
        self.event_queue.put(event)
        
        # 触发回调
        for callback in self.callbacks.get('on_event', []):
            try:
                callback(event)
            except Exception as e:
                print(f"事件回调执行失败: {e}")

    def _sanitize_data(self, data: Optional[Dict]):
        """移除或裁剪 data 中的大字段，防止日志被完整 HTML 填满"""
        if not data:
            return data
        try:
            result = {}
            for k, v in data.items():
                if isinstance(v, str):
                    if len(v) > 2000:
                        result[k] = v[:1000] + '... (truncated)'
                    else:
                        result[k] = v
                else:
                    result[k] = v
            # 特殊处理 html 字段
            if 'html' in result:
                result['html_length'] = len(result.get('html') or '')
                result.pop('html', None)
            return result
        except Exception:
            return {}

    def log_network_request(self, url: str, method: str, headers: Optional[Dict] = None, size: int = 0):
        """记录网络请求"""
        if not self.enable_network_log:
            return
        
        self.stats['total_requests'] += 1
        self.stats['urls_visited'].add(url)
        
        request_log = {
            'timestamp': datetime.now().isoformat(),
            'type': 'request',
            'url': url,
            'method': method,
            'headers': headers or {},
            'size': size
        }
        
        self.network_logs.append(request_log)
        
        # 触发回调
        for callback in self.callbacks.get('on_network_request', []):
            try:
                callback(request_log)
            except Exception:
                pass

    def log_network_response(self, url: str, status_code: int, size: int, duration_ms: float, headers: Optional[Dict] = None):
        """记录网络响应"""
        if not self.enable_network_log:
            return
        
        self.stats['total_responses'] += 1
        self.stats['total_bytes'] += size
        
        response_log = {
            'timestamp': datetime.now().isoformat(),
            'type': 'response',
            'url': url,
            'status': status_code,
            'size': size,
            'duration_ms': duration_ms,
            'headers': headers or {}
        }
        
        self.network_logs.append(response_log)
        
        # 检查性能告警
        if duration_ms > self.performance_thresholds['slow_request']:
            self.log_event(
                'warning',
                'network',
                f'请求缓慢: {url}',
                {'duration_ms': duration_ms, 'threshold': self.performance_thresholds['slow_request']}
            )
            self._trigger_performance_alert('slow_request', {
                'url': url,
                'duration_ms': duration_ms,
                'threshold': self.performance_thresholds['slow_request']
            })
        
        if size > self.performance_thresholds['large_response']:
            self.log_event(
                'warning',
                'network',
                f'响应过大: {url}',
                {'size': size, 'threshold': self.performance_thresholds['large_response']}
            )
        
        # 触发回调
        for callback in self.callbacks.get('on_network_response', []):
            try:
                callback(response_log)
            except Exception:
                pass

    def log_error(self, component: str, message: str, error_type: Optional[str] = None, details: Optional[Dict] = None):
        """记录错误"""
        self.stats['total_errors'] += 1
        
        if error_type:
            self.stats['error_counts'][error_type] = self.stats['error_counts'].get(error_type, 0) + 1
        
        self.log_event('error', component, message, details or {})
        
        # 触发回调
        for callback in self.callbacks.get('on_error', []):
            try:
                callback({'component': component, 'message': message, 'type': error_type, 'details': details})
            except Exception:
                pass

    def log_page_performance(self, url: str, metrics: Dict[str, float]):
        """
        记录页面性能指标
        
        Args:
            url: 页面URL
            metrics: 性能指标 (dns, tcp, request, response, dom, total等)
        """
        total_time = metrics.get('total', 0)
        
        if total_time > self.performance_thresholds['slow_page']:
            self.log_event(
                'warning',
                'performance',
                f'页面加载缓慢: {url}',
                {'metrics': metrics, 'threshold': self.performance_thresholds['slow_page']}
            )
            self._trigger_performance_alert('slow_page', {
                'url': url,
                'metrics': metrics,
                'threshold': self.performance_thresholds['slow_page']
            })
        else:
            self.log_event(
                'success',
                'performance',
                f'页面已加载: {url}',
                {'metrics': metrics}
            )

    def register_callback(self, event_type: str, callback: Callable):
        """注册回调函数"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)

    def set_performance_threshold(self, threshold_type: str, value: float):
        """设置性能阈值"""
        if threshold_type in self.performance_thresholds:
            self.performance_thresholds[threshold_type] = value

    def _trigger_performance_alert(self, alert_type: str, data: Dict):
        """触发性能告警"""
        for callback in self.callbacks.get('on_performance_alert', []):
            try:
                callback({'type': alert_type, 'data': data})
            except Exception:
                pass

    def _process_events(self):
        """处理事件队列的后台线程"""
        while self.running:
            try:
                event = self.event_queue.get(timeout=1)
                # 这里可以添加事件处理逻辑，如持久化、远程日志等
            except queue.Empty:
                pass
            except Exception as e:
                print(f"事件处理失败: {e}")

    def get_events(self, level: Optional[str] = None, component: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        获取事件日志
        
        Args:
            level: 按级别过滤
            component: 按组件过滤
            limit: 返回数量限制
            
        Returns:
            事件列表
        """
        events = list(self.events)
        
        if level:
            events = [e for e in events if e.level == level]
        if component:
            events = [e for e in events if e.component == component]
        
        events = events[-limit:]
        return [e.to_dict() for e in events]

    def get_network_logs(self, log_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取网络日志"""
        logs = list(self.network_logs)
        
        if log_type:
            logs = [l for l in logs if l.get('type') == log_type]
        
        return logs[-limit:]

    def get_statistics(self) -> Dict:
        """获取统计数据"""
        return {
            'total_requests': self.stats['total_requests'],
            'total_responses': self.stats['total_responses'],
            'total_errors': self.stats['total_errors'],
            'total_bytes': self.stats['total_bytes'],
            'urls_visited_count': len(self.stats['urls_visited']),
            'error_counts': dict(self.stats['error_counts']),
            'duration_seconds': (datetime.fromisoformat(datetime.now().isoformat()) - 
                               datetime.fromisoformat(self.stats['start_time'])).total_seconds()
        }

    def get_summary(self) -> Dict:
        """获取调试摘要"""
        events = self.get_events(limit=50)
        network_logs = self.get_network_logs(limit=20)
        
        errors_by_type = {}
        warnings_list = []
        
        for event in events:
            if event['level'] == 'error':
                error_type = event.get('data', {}).get('type', 'unknown')
                errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1
            elif event['level'] == 'warning':
                warnings_list.append({
                    'component': event['component'],
                    'message': event['message'],
                    'timestamp': event['timestamp']
                })
        
        return {
            'statistics': self.get_statistics(),
            'recent_errors': list(filter(lambda e: e['level'] == 'error', events))[:10],
            'recent_warnings': warnings_list[:10],
            'network_summary': {
                'total_requests': len([l for l in network_logs if l.get('type') == 'request']),
                'total_responses': len([l for l in network_logs if l.get('type') == 'response']),
                'avg_response_time': self._calc_avg_response_time(network_logs),
                'total_bytes_transferred': sum(l.get('size', 0) for l in network_logs if l.get('type') == 'response')
            }
        }

    def _calc_avg_response_time(self, logs: List[Dict]) -> float:
        """计算平均响应时间"""
        response_logs = [l for l in logs if l.get('type') == 'response']
        if not response_logs:
            return 0
        
        total_time = sum(l.get('duration_ms', 0) for l in response_logs)
        return total_time / len(response_logs)

    def export_report(self, output_file: str):
        """导出调试报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': self.get_summary(),
            'events': self.get_events(limit=200),
            'network_logs': self.get_network_logs(limit=200)
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def stop(self):
        """停止调试器"""
        self.running = False
        self.event_thread.join(timeout=2)


class DebugViewer:
    """调试查看器 - 用于在GUI中展示调试信息"""
    
    def __init__(self, debugger: RealTimeDebugger):
        self.debugger = debugger
        self.update_callbacks = []
    
    def register_update_callback(self, callback: Callable):
        """注册UI更新回调"""
        self.update_callbacks.append(callback)
    
    def get_dashboard_data(self) -> Dict:
        """获取仪表板数据"""
        summary = self.debugger.get_summary()
        return {
            'title': '爬虫实时监控',
            'summary': summary,
            'timestamp': datetime.now().isoformat()
        }
    
    def trigger_ui_update(self, data: Dict):
        """触发UI更新"""
        for callback in self.update_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"UI更新失败: {e}")
