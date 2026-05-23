"""
调试管理器 - 提供详细的日志和错误追踪（输出到终端和GUI）
"""
import logging
import traceback
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class DebugManager:
    """调试管理器 - 提供详细的调试信息"""
    
    def __init__(self, log_file: str = "./logs/debug.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 清除已有的handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # 配置日志 - 详细输出到终端
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)  # 确保输出到stdout
            ],
            force=True  # 强制重新配置
        )
        
        # 确保根日志级别为DEBUG
        logging.root.setLevel(logging.DEBUG)
        
        self.logger = logging.getLogger('AdvancedWebAnalyzer')
        self.logger.setLevel(logging.DEBUG)
        self.call_stack = []
        self.error_count = 0
        
        # GUI引用（稍后设置）
        self.debug_gui = None
        
        print("[调试] 调试系统已初始化，所有信息将输出到终端")
    
    def set_debug_gui(self, debug_gui):
        """设置调试GUI引用"""
        self.debug_gui = debug_gui
        print("[调试] 调试GUI已连接")
    
    def log_function_call(self, func_name: str, args: dict = None):
        """记录函数调用"""
        args_str = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
        msg = f"[调用] {func_name}({args_str})"
        self.logger.debug(msg)
        print(msg)

        # 记录到调用栈
        self.call_stack.append({
            'function': func_name,
            'args': args,
            'time': datetime.now().isoformat()
        })

        # 更新GUI - 使用try-except确保GUI错误不影响系统运行
        if self.debug_gui:
            try:
                # 更新调用栈显示
                self.debug_gui.log_call_stack(self.call_stack)
                # 更新函数调用日志
                self.debug_gui.log_function_call(func_name, args)
            except Exception as e:
                # GUI更新失败时,记录错误但不影响程序运行
                print(f"[警告] 调试GUI更新失败: {e}")
    
    def log_function_return(self, func_name: str, result: any = None):
        """记录函数返回"""
        msg = f"[返回] {func_name} -> {result}"
        self.logger.debug(msg)
        print(msg)

        # 更新GUI - 使用try-except确保GUI错误不影响系统运行
        if self.debug_gui:
            try:
                self.debug_gui.log_function_return(func_name, result)
            except Exception as e:
                # GUI更新失败时,记录错误但不影响程序运行
                print(f"[警告] 调试GUI更新失败: {e}")
        
        if self.call_stack and self.call_stack[-1]['function'] == func_name:
            self.call_stack.pop()
    
    def log_error(self, func_name: str, error: Exception, context: dict = None):
        """记录错误"""
        self.error_count += 1
        error_info = {
            'function': func_name,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'context': context,
            'time': datetime.now().isoformat()
        }

        msg1 = f"[错误] {func_name}: {error}"
        self.logger.error(msg1)
        print(msg1)

        msg2 = f"[堆栈]\n{traceback.format_exc()}"
        self.logger.debug(msg2)
        print(msg2)

        # 更新GUI - 使用try-except确保GUI错误不影响系统运行
        if self.debug_gui:
            try:
                self.debug_gui.log_error(error_info)
            except Exception as gui_error:
                # GUI更新失败时,记录错误但不影响程序运行
                print(f"[警告] 调试GUI更新失败: {gui_error}")
        
        # 保存错误详情到单独文件
        self._save_error_details(error_info)
    
    def log_step(self, step_name: str, details: dict = None):
        """记录步骤"""
        details_str = ", ".join(f"{k}={v}" for k, v in (details or {}).items())
        msg = f"[步骤] {step_name} - {details_str}"
        self.logger.info(msg)
        print(msg)
    
    def log_data(self, data_name: str, data: any):
        """记录数据"""
        # 截断长数据的显示
        data_display = str(data)[:100] if isinstance(data, (str, list, dict)) else str(data)
        msg = f"[数据] {data_name} = {data_display}"
        self.logger.debug(msg)
        print(msg)

        # 更新GUI - 使用try-except确保GUI错误不影响系统运行
        if self.debug_gui:
            try:
                self.debug_gui.log_data(data_name, data_display)
            except Exception as e:
                # GUI更新失败时,记录错误但不影响程序运行
                print(f"[警告] 调试GUI更新失败: {e}")
    
    def log_progress(self, current: int, total: int, message: str = ""):
        """记录进度"""
        percentage = (current / total * 100) if total > 0 else 0
        msg = f"[进度] {current}/{total} ({percentage:.1f}%) {message}"
        self.logger.info(msg)
        print(msg)
    
    def get_call_stack(self) -> list:
        """获取调用栈"""
        return self.call_stack.copy()
    
    def get_error_count(self) -> int:
        """获取错误数量"""
        return self.error_count
    
    def _save_error_details(self, error_info: dict):
        """保存错误详情"""
        error_file = self.log_file.parent / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            import json
            with open(error_file, 'w', encoding='utf-8') as f:
                json.dump(error_info, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


# 全局调试管理器实例
debug = DebugManager()