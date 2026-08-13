"""
ima_client.py
=============
IMA 个人知识库 pyautogui 自动化客户端（视觉感知版）

工作方式：
  每步关键操作 → 先截图 → 请求 WorkBuddy AI 分析坐标 → 点击
  如果 AI 定位超时，退回硬编码坐标兜底（基于 2560x1600 / left=891 窗口）

功能：
  - upload(file_path)                     上传文件到知识库
  - search(keyword)                       搜索知识库
  - search_and_download(keyword, save_dir) 搜索并下载

调用方式：
  from ima_client import upload, search, search_and_download
"""

import os
import sys
import time

# ── 路径 ──────────────────────────────────────────────────────────────────────
CLAW_DIR  = r"C:\Users\qu\WorkBuddy\Claw"
SKILL_DIR = os.path.join(CLAW_DIR, r".codebuddy\skills\ima-knowledge-base")
sys.path.insert(0, CLAW_DIR)
sys.path.insert(0, SKILL_DIR)

# ── 延迟初始化：pyautogui / pyperclip 只在第一次真正操作时才 import ──────────
# 原因：shell_logger → visible_runner 会先后台 subprocess.run() 一次捕获日志，
# 模块顶层的 pyautogui 操作若在后台执行会点到错误窗口。
# 延迟到函数调用时才 import，后台那次不会触发任何 GUI 操作。
_pyautogui   = None
_pyperclip   = None

def _gui():
    """首次调用时 import 并初始化 pyautogui，之后复用同一实例"""
    global _pyautogui
    if _pyautogui is None:
        import pyautogui as _pag
        _pag.FAILSAFE = True
        _pag.PAUSE    = 0.3
        _pyautogui = _pag
    return _pyautogui

def _clip():
    """首次调用时 import pyperclip"""
    global _pyperclip
    if _pyperclip is None:
        import pyperclip as _pc
        _pyperclip = _pc
    return _pyperclip

# ── 视觉感知模块（延迟导入，避免循环） ───────────────────────────────────────
_vision = None
def _get_vision():
    global _vision
    if _vision is None:
        try:
            import ima_vision as v
            _vision = v
            print("[ima_client] ima_vision 已加载（视觉感知模式）")
        except ImportError as e:
            print(f"[ima_client] ima_vision 不可用，使用硬编码坐标兜底: {e}")
    return _vision

# ── 窗口信息缓存（兜底坐标基于此） ───────────────────────────────────────────
_win_info = {
    "left":   891,
    "top":    0,
    "right":  2569,
    "bottom": 1537,
    "width":  1678,
    "height": 1537,
}

# ── 硬编码兜底坐标表（相对比例） ─────────────────────────────────────────────
# 格式: "按钮名": (rel_x, rel_y)
_FALLBACK = {
    "知识库灯泡":   (0.024, 0.15),
    "上传按钮":     (0.024, 0.22),
    "搜索按钮":     (0.940, 0.055),
    "下载按钮":     (0.960, 0.055),
    "第一个卡片":   (0.18,  0.28),
    "标题栏":       (0.5,   0.02),
}


def refresh_window():
    """重新探测 IMA 窗口坐标，更新缓存；同时记录 hwnd 供 focus 使用"""
    try:
        import win32gui
        results = []
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if 'ima' in t.lower() or '知识库' in t or 'copilot' in t.lower():
                    r = win32gui.GetWindowRect(hwnd)
                    w, h = r[2]-r[0], r[3]-r[1]
                    if w > 200 and h > 200:
                        results.append((hwnd, t, r))
        win32gui.EnumWindows(_cb, None)
        if results:
            hwnd, title, r = results[0]
            _win_info.update({
                "hwnd":  hwnd,
                "left": r[0], "top": r[1],
                "right": r[2], "bottom": r[3],
                "width": r[2]-r[0], "height": r[3]-r[1],
            })
            print(f"[ima_client] 窗口已更新: {title} hwnd={hwnd} → {r}")
            return True
    except Exception as e:
        print(f"[ima_client] refresh_window 失败: {e}")
    return False


def bring_to_front():
    """
    把 IMA 窗口强制拉到前台（远程操作场景必须）。
    先 ShowWindow 恢复最小化，再 SetForegroundWindow。
    """
    hwnd = _win_info.get("hwnd")
    if not hwnd:
        refresh_window()
        hwnd = _win_info.get("hwnd")
    if not hwnd:
        print("[ima_client] bring_to_front: 未找到 IMA 窗口")
        return False
    try:
        import win32gui
        import win32con
        # 若最小化则先还原
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        # 强制前置
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        print(f"[ima_client] IMA 已前置 hwnd={hwnd}")
        return True
    except Exception as e:
        # SetForegroundWindow 有时因焦点限制失败，备用方案：模拟 Alt 键
        print(f"[ima_client] SetForegroundWindow 失败({e})，尝试备用方案")
        try:
            import win32api, win32con
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)          # Alt down
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU, 0,
                                 win32con.KEYEVENTF_KEYUP, 0)         # Alt up
            time.sleep(0.5)
            print(f"[ima_client] 备用前置成功 hwnd={hwnd}")
            return True
        except Exception as e2:
            print(f"[ima_client] bring_to_front 全部失败: {e2}")
            return False


def _abs(rel_x, rel_y):
    """相对比例 → 屏幕绝对坐标"""
    x = _win_info["left"] + int(_win_info["width"]  * rel_x)
    y = _win_info["top"]  + int(_win_info["height"] * rel_y)
    return x, y


def _locate(target_name: str, target_desc: str, hint: str = "") -> tuple[int, int]:
    """
    定位按钮坐标：
      1. 优先调用 ima_vision（截图 → AI 分析）
      2. AI 失败/超时 → 读 _FALLBACK 硬编码兜底
    返回 (x, y) 屏幕绝对坐标。
    """
    vision = _get_vision()
    if vision:
        print(f"[ima_client] 视觉定位: {target_desc}")
        coords = vision.locate_button(
            target  = target_desc,
            hint    = hint or "IMA 个人知识库 Windows 客户端",
            timeout = 90,
        )
        if coords:
            return coords
        print(f"[ima_client] 视觉定位失败，启用兜底坐标: {target_name}")

    # 兜底
    rel = _FALLBACK.get(target_name)
    if rel:
        x, y = _abs(*rel)
        print(f"[ima_client] 兜底坐标 {target_name}: ({x}, {y})")
        return x, y

    # 最终兜底：窗口中心
    cx = _win_info["left"] + _win_info["width"]  // 2
    cy = _win_info["top"]  + _win_info["height"] // 2
    print(f"[ima_client] 无坐标信息，使用窗口中心: ({cx}, {cy})")
    return cx, cy


def _click(x: int, y: int, desc: str = "", double: bool = False):
    print(f"[ima_client] {'双击' if double else '点击'} {desc} ({x}, {y})")
    pag = _gui()
    if double:
        pag.doubleClick(x, y)
    else:
        pag.click(x, y)
    time.sleep(0.5)


def _screenshot_step(label: str) -> str:
    """每步操作后截图存档，返回路径"""
    vision = _get_vision()
    if vision:
        path = vision.take_screenshot(f"step_{label}")
        print(f"[ima_client] 步骤截图: {path}")
        return path
    return ""


# ═════════════════════════════════════════════════════════════════════════════
# 公共接口
# ═════════════════════════════════════════════════════════════════════════════

def focus_kb():
    """切换到「个人知识库」页面（先把 IMA 拉到前台）"""
    refresh_window()
    bring_to_front()   # ← 远程操作必须：强制 IMA 到前台
    time.sleep(0.5)

    # 点标题栏获焦
    x, y = _locate("标题栏", "IMA 窗口标题栏空白区域，用于获取焦点")
    _click(x, y, "IMA标题栏获焦")
    time.sleep(0.3)

    # 点知识库图标
    x, y = _locate(
        "知识库灯泡",
        "左侧竖栏第2个按钮，灯泡形状的图标，代表「个人知识库」",
        hint="IMA 左侧有一列垂直图标按钮，从上到下依次是：对话、知识库、..."
    )
    _click(x, y, "知识库灯泡")
    time.sleep(1.0)
    _screenshot_step("focus_kb")
    print("[ima_client] 已切换到个人知识库")


def upload(file_path: str, wait_sec: int = 8) -> bool:
    """
    上传文件到 IMA 个人知识库。
    流程：focus_kb → 点上传按钮 → 文件对话框粘贴路径 → 回车
    """
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        print(f"[ima_client] 文件不存在: {file_path}")
        return False

    print(f"[ima_client] 准备上传: {file_path}")
    focus_kb()
    time.sleep(0.5)

    # 定位上传按钮
    x, y = _locate(
        "上传按钮",
        "左侧竖栏中带加号「+」的纸张文件图标，点击后弹出文件上传对话框",
        hint="IMA 知识库页面，左侧有一列图标，其中一个是带+号的纸张图标"
    )
    _click(x, y, "上传按钮(+纸张)")
    time.sleep(1.8)  # 等文件对话框弹出

    _screenshot_step("upload_dialog_opened")

    # 粘贴路径到文件对话框
    _clip().copy(file_path)
    _gui().hotkey('ctrl', 'a')
    time.sleep(0.2)
    _gui().hotkey('ctrl', 'v')
    time.sleep(0.3)
    _gui().press('enter')
    time.sleep(1.0)

    print(f"[ima_client] 等待上传完成（{wait_sec}s）...")
    time.sleep(wait_sec)

    _screenshot_step("upload_done")
    print("[ima_client] 上传触发完成")
    return True


def search(keyword: str) -> bool:
    """
    搜索知识库文件。
    流程：focus_kb → 点搜索按钮 → 输入关键词 → 回车
    """
    print(f"[ima_client] 搜索: {keyword}")
    focus_kb()
    time.sleep(0.5)

    # 定位搜索按钮
    x, y = _locate(
        "搜索按钮",
        "右上角的放大镜搜索图标，点击后弹出搜索输入框",
        hint="IMA 知识库界面右上角有一排小图标：搜索、上传等"
    )
    _click(x, y, "搜索按钮")
    time.sleep(0.8)

    _screenshot_step("search_box_opened")

    # 输入关键词
    _gui().hotkey('ctrl', 'a')
    time.sleep(0.1)
    _clip().copy(keyword)
    _gui().hotkey('ctrl', 'v')
    time.sleep(0.3)
    _gui().press('enter')
    time.sleep(1.5)

    _screenshot_step("search_results")
    print(f"[ima_client] 已搜索: {keyword}")
    return True


def open_first_result() -> bool:
    """双击打开搜索结果中第一个文件卡片"""

    # 先截图让 AI 看一下搜索结果
    x, y = _locate(
        "第一个卡片",
        "搜索结果列表中第一个文件卡片，左上角位置，可能显示文件名和缩略图",
        hint="IMA 知识库搜索结果页，以卡片网格展示文件，第一个卡片在左上区域"
    )
    _click(x, y, "第一个结果卡片", double=True)
    time.sleep(2.0)

    _screenshot_step("first_result_opened")
    print("[ima_client] 已打开第一个结果")
    return True


def download_current(save_dir: str = None) -> bool:
    """下载当前打开的文件"""
    print("[ima_client] 准备下载...")

    # 让 AI 看看当前页面，找下载按钮
    x, y = _locate(
        "下载按钮",
        "当前文件详情页顶部工具栏里的下载按钮，通常是向下箭头图标或「下载」文字",
        hint="IMA 已打开一个 PDF 文件的详情页，顶部有工具栏，其中有下载相关的按钮"
    )
    _click(x, y, "下载按钮")
    time.sleep(1.5)

    _screenshot_step("download_clicked")

    # 如果弹出保存对话框，指定路径
    if save_dir:
        save_dir = os.path.abspath(save_dir)
        os.makedirs(save_dir, exist_ok=True)
        _clip().copy(save_dir)
        _gui().hotkey('ctrl', 'a')
        time.sleep(0.2)
        _gui().hotkey('ctrl', 'v')
        time.sleep(0.3)
        _gui().press('enter')
        time.sleep(1.0)
        print(f"[ima_client] 下载到: {save_dir}")

    _screenshot_step("download_done")
    return True


def search_and_download(keyword: str, save_dir: str = None) -> bool:
    """一键：搜索 → 打开第一个结果 → 下载"""
    if not search(keyword):
        return False
    time.sleep(1.0)
    if not open_first_result():
        return False
    time.sleep(1.0)
    return download_current(save_dir)


# ── 调试工具 ──────────────────────────────────────────────────────────────────
def print_coords():
    """打印当前窗口下各关键兜底坐标"""
    refresh_window()
    print("\n=== IMA 兜底坐标（当前窗口）===")
    for name, (rx, ry) in _FALLBACK.items():
        x, y = _abs(rx, ry)
        print(f"  {name}: ({x}, {y})  [相对={rx:.3f},{ry:.3f}]")
    print(f"\n  窗口: ({_win_info['left']},{_win_info['top']}) "
          f"→ ({_win_info['right']},{_win_info['bottom']}) "
          f"尺寸={_win_info['width']}x{_win_info['height']}")


if __name__ == '__main__':
    print_coords()
