"""
ima_steps.py
============
IMA 具体操作步骤，每个类对应一个原子动作。

所有类继承 IMAAction，只实现 _execute()。
每次执行前，基类自动完成：
  1. 探测+前置 IMA 窗口
  2. 截图
  3. 请求 AI 分析坐标（vision_task.json → vision_result.json）
  4. 调用 _execute(coords, win)
  5. 截图确认

注册到工厂：
  IMAActionFactory.create("focus")
  IMAActionFactory.create("upload",   file_path="C:/xxx.pdf")
  IMAActionFactory.create("search",   keyword="关键词")
  IMAActionFactory.create("download", save_dir="C:/downloads")
  IMAActionFactory.create("open_first")
"""

import os
import sys
import time

import pyautogui
import pyperclip

# 引入基类和工厂
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ima_action import IMAAction, IMAActionFactory, _abs, _log


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — 前置 + 切换到知识库页面
# ══════════════════════════════════════════════════════════════════════════════

class FocusAction(IMAAction):
    """
    把 IMA 拉到前台，点击「知识库」图标，确认进入知识库页面。
    这是所有其他步骤的前置步骤，每次工作流必须先执行。
    """
    name          = "focus"
    _target       = "左侧竖栏中的「个人知识库」图标，通常是灯泡形状，点击后进入知识库页面"
    _hint         = ("IMA 客户端左侧有一列垂直图标导航栏，从上到下依次是：对话、知识库（灯泡）、"
                     "设置等。知识库图标在第2个位置附近。")
    _fallback_key = "知识库灯泡"

    def _execute(self, coords, win):
        if coords:
            x, y = coords
            _log(self.name, f"点击知识库图标 ({x}, {y})")
            pyautogui.click(x, y)
            time.sleep(1.2)
        else:
            _log(self.name, "未能定位知识库图标，跳过点击")
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — 上传文件
# ══════════════════════════════════════════════════════════════════════════════

class UploadAction(IMAAction):
    """
    点击上传按钮（带+号纸张图标）→ 系统文件对话框 → 粘贴路径 → 回车。
    """
    name          = "upload"
    _target       = ("左侧竖栏中带加号「+」的纸张图标，这是上传文件按钮，"
                     "点击后会弹出系统文件选择对话框")
    _hint         = ("IMA 个人知识库页面，左侧图标列中有一个纸张+加号的上传图标，"
                     "通常在知识库灯泡图标下方附近。")
    _fallback_key = "上传按钮"

    def __init__(self, file_path: str, **kwargs):
        super().__init__(**kwargs)
        self.file_path = os.path.abspath(file_path)

    def _execute(self, coords, win):
        if not os.path.exists(self.file_path):
            _log(self.name, f"文件不存在: {self.file_path}")
            return False

        if coords:
            x, y = coords
            _log(self.name, f"点击上传按钮 ({x}, {y})")
            pyautogui.click(x, y)
        else:
            _log(self.name, "未能定位上传按钮，中止")
            return False

        # 等待文件对话框弹出
        time.sleep(1.8)

        # 粘贴文件路径
        _log(self.name, f"粘贴路径: {self.file_path}")
        pyperclip.copy(self.file_path)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.0)

        _log(self.name, "等待上传处理（8s）...")
        time.sleep(8)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — 搜索
# ══════════════════════════════════════════════════════════════════════════════

class SearchAction(IMAAction):
    """
    点击右上角搜索图标 → 输入关键词 → 回车，等待搜索结果出现。
    """
    name          = "search"
    _target       = ("右上角的放大镜搜索图标，点击后会出现搜索输入框，"
                     "用来搜索知识库中的文件")
    _hint         = ("IMA 知识库界面右上角有一排小图标按钮：搜索（放大镜）、"
                     "上传、设置等，搜索按钮在最左边或靠左位置。")
    _fallback_key = "搜索按钮"

    def __init__(self, keyword: str, **kwargs):
        super().__init__(**kwargs)
        self.keyword = keyword

    def _execute(self, coords, win):
        if coords:
            x, y = coords
            _log(self.name, f"点击搜索按钮 ({x}, {y})")
            pyautogui.click(x, y)
        else:
            _log(self.name, "未能定位搜索按钮，中止")
            return False

        time.sleep(0.8)

        # 输入关键词
        _log(self.name, f"输入关键词: {self.keyword}")
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyperclip.copy(self.keyword)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")

        _log(self.name, "等待搜索结果（2s）...")
        time.sleep(2.0)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — 打开第一个搜索结果
# ══════════════════════════════════════════════════════════════════════════════

class OpenFirstAction(IMAAction):
    """
    在搜索结果中定位第一个文件卡片并双击打开。
    AI 会看搜索结果截图，找到第一个卡片的坐标。
    """
    name          = "open_first"
    _target       = ("搜索结果页面中第一个文件卡片，位于左上角区域，"
                     "卡片上显示文件名和缩略图，双击可打开文件详情")
    _hint         = ("IMA 知识库搜索结果页，文件以卡片网格方式展示，"
                     "第一个卡片在页面左上区域（内容区域左上角）。")
    _fallback_key = "第一个卡片"

    def _execute(self, coords, win):
        if coords:
            x, y = coords
            _log(self.name, f"双击第一个结果卡片 ({x}, {y})")
            pyautogui.doubleClick(x, y)
        else:
            _log(self.name, "未能定位第一个卡片，中止")
            return False

        _log(self.name, "等待文件详情页加载（2.5s）...")
        time.sleep(2.5)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — 下载当前文件
# ══════════════════════════════════════════════════════════════════════════════

class DownloadAction(IMAAction):
    """
    在文件详情页找到下载按钮并点击，可选指定保存目录。
    AI 会看文件详情页截图，找到顶部工具栏的下载按钮。
    """
    name          = "download"
    _target       = ("文件详情页顶部工具栏中的下载按钮，"
                     "通常是向下箭头图标或带「下载」文字的按钮")
    _hint         = ("IMA 已打开一个文件的详情/预览页面，"
                     "顶部有操作工具栏，其中有下载（向下箭头）按钮。")
    _fallback_key = "下载按钮"

    def __init__(self, save_dir: str = None, **kwargs):
        super().__init__(**kwargs)
        self.save_dir = os.path.abspath(save_dir) if save_dir else None

    def _execute(self, coords, win):
        if coords:
            x, y = coords
            _log(self.name, f"点击下载按钮 ({x}, {y})")
            pyautogui.click(x, y)
        else:
            _log(self.name, "未能定位下载按钮，中止")
            return False

        time.sleep(1.5)

        # 如果弹出保存对话框，填入目标目录
        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            _log(self.name, f"保存到: {self.save_dir}")
            pyperclip.copy(self.save_dir)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(1.0)

        _log(self.name, "等待下载（3s）...")
        time.sleep(3.0)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# 注册到工厂
# ══════════════════════════════════════════════════════════════════════════════

IMAActionFactory.register("focus",      FocusAction)
IMAActionFactory.register("upload",     UploadAction)
IMAActionFactory.register("search",     SearchAction)
IMAActionFactory.register("open_first", OpenFirstAction)
IMAActionFactory.register("download",   DownloadAction)

# ── 自测 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("已注册的 Action:", list(IMAActionFactory._registry.keys()))
    print("导入成功，工厂模式就绪。")
