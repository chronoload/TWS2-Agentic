"""
ima_vision.py
=============
IMA 自动化的视觉感知层。

工作机制（无需外部 API key）：
  1. 截取当前屏幕（或 IMA 窗口区域）
  2. 把截图路径 + 任务描述写入  vision_task.json
  3. 轮询等待 WorkBuddy AI 读图分析，把结果写回 vision_result.json
  4. 返回按钮坐标给调用方（ima_client.py）

vision_task.json 格式（脚本 → AI）：
{
  "id":        "unique-task-id",
  "screenshot": "C:/...debug_screenshots/ima_vision_xxx.png",
  "target":    "搜索按钮（右上角放大镜图标）",
  "hint":      "IMA 个人知识库界面，右上角有一排小图标",
  "status":    "pending"   ← AI 读到后把 status 改为 done
}

vision_result.json 格式（AI → 脚本）：
{
  "id":         "same-task-id",
  "x":          2468,
  "y":          84,
  "confidence": 0.92,
  "desc":       "右上角搜索按钮，放大镜图标",
  "status":     "done"
}
"""

import os
import sys
import json
import time
import uuid
import datetime

# ── 延迟初始化：pyautogui / PIL 只在第一次截图时才 import ────────────────────
_pyautogui = None

def _gui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui as _pag
        _pyautogui = _pag
    return _pyautogui

# ── 路径常量 ──────────────────────────────────────────────────────────────────
CLAW_DIR       = r"C:\Users\qu\WorkBuddy\Claw"
SCREENSHOT_DIR = os.path.join(CLAW_DIR, "debug_screenshots")
TASK_FILE      = os.path.join(CLAW_DIR, "vision_task.json")
RESULT_FILE    = os.path.join(CLAW_DIR, "vision_result.json")

# ── 超时配置 ──────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 120   # 秒：等待 AI 分析的最长时间
POLL_INTERVAL   = 1.0   # 秒：轮询间隔


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def take_screenshot(label: str = "ima_vision", region=None) -> str:
    """
    截图并保存到 debug_screenshots/。
    region: (left, top, width, height) 截取指定区域；None=全屏
    返回截图文件绝对路径。
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    fname = f"{label}_{_ts()}.png"
    fpath = os.path.join(SCREENSHOT_DIR, fname)

    if region:
        screenshot = _gui().screenshot(region=region)
    else:
        screenshot = _gui().screenshot()

    screenshot.save(fpath)
    print(f"[ima_vision] 截图已保存: {fpath}")
    return fpath


def ask_ai(target: str, hint: str = "", screenshot_path: str = None,
           timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    向 WorkBuddy AI 请求：在截图中找到目标按钮的坐标。

    参数：
      target:          要找的按钮描述，例如 "右上角搜索放大镜按钮"
      hint:            界面背景提示，帮助 AI 理解上下文
      screenshot_path: 截图路径；None=自动截图
      timeout:         等待 AI 响应的秒数

    返回：
      {"x": int, "y": int, "confidence": float, "desc": str}
      失败时返回 {"x": None, "y": None, "error": str}
    """
    # 1. 截图
    if not screenshot_path:
        screenshot_path = take_screenshot(f"ima_ask_{target[:10].replace(' ', '_')}")

    # 2. 写任务文件
    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":          task_id,
        "screenshot":  screenshot_path,
        "target":      target,
        "hint":        hint or "IMA 个人知识库 Windows 客户端界面",
        "status":      "pending",
        "created_at":  _ts(),
    }
    with open(TASK_FILE, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    print(f"[ima_vision] 任务已写入: {TASK_FILE}")
    print(f"[ima_vision] 等待 AI 分析: {target}")

    # 3. 轮询 vision_result.json
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        if not os.path.exists(RESULT_FILE):
            continue
        try:
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                result = json.load(f)
            # 确认是对应这次任务的结果
            if result.get("id") == task_id and result.get("status") == "done":
                print(f"[ima_vision] AI 返回坐标: ({result.get('x')}, {result.get('y')}) "
                      f"置信度={result.get('confidence', '?')}")
                # 清理任务文件
                _cleanup()
                return result
        except (json.JSONDecodeError, IOError):
            continue

    # 超时
    print(f"[ima_vision] 超时 ({timeout}s)，未收到 AI 响应")
    _cleanup()
    return {"x": None, "y": None, "error": f"timeout after {timeout}s",
            "id": task_id, "status": "timeout"}


def _cleanup():
    """清理任务/结果文件，避免下次误读旧数据"""
    for f in (TASK_FILE, RESULT_FILE):
        try:
            if os.path.exists(f):
                os.remove(f)
        except OSError:
            pass


def answer_task(result_dict: dict):
    """
    [AI 侧调用] 把分析结果写回 vision_result.json。
    AI 读到 vision_task.json 后，调用此函数写入坐标。

    result_dict 需包含：
      x, y, confidence(可选), desc(可选)
    """
    if not os.path.exists(TASK_FILE):
        print("[ima_vision] 没有待处理的任务文件")
        return False

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        task = json.load(f)

    result = {
        "id":          task["id"],
        "x":           result_dict.get("x"),
        "y":           result_dict.get("y"),
        "confidence":  result_dict.get("confidence", 1.0),
        "desc":        result_dict.get("desc", ""),
        "status":      "done",
        "answered_at": _ts(),
    }
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[ima_vision] 结果已写回: x={result['x']}, y={result['y']}")
    return True


def read_pending_task() -> dict | None:
    """
    [AI 侧调用] 读取当前待处理的视觉任务。
    返回 task dict，或 None（无待处理任务）。
    """
    if not os.path.exists(TASK_FILE):
        return None
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as f:
            task = json.load(f)
        if task.get("status") == "pending":
            return task
    except (json.JSONDecodeError, IOError):
        pass
    return None


# ── 便捷函数：截图并立即请求 AI 分析（带重试）────────────────────────────────
def locate_button(target: str, hint: str = "",
                  region=None, retries: int = 2,
                  timeout: int = DEFAULT_TIMEOUT) -> tuple[int, int] | None:
    """
    截图 → 请求 AI 定位按钮 → 返回 (x, y) 绝对坐标。
    失败时返回 None。

    参数：
      target:  按钮描述
      hint:    界面背景提示
      region:  截图区域 (left, top, w, h)；None=全屏
      retries: 失败重试次数
      timeout: 单次等待超时秒数
    """
    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"[ima_vision] 第 {attempt+1} 次重试...")
            time.sleep(2)
        screenshot_path = take_screenshot(
            f"ima_locate_{target[:8].replace(' ', '_')}", region=region
        )
        result = ask_ai(target, hint, screenshot_path, timeout)
        x, y = result.get("x"), result.get("y")
        if x is not None and y is not None:
            return int(x), int(y)
        print(f"[ima_vision] 本次未能定位: {result.get('error', '未知错误')}")

    print(f"[ima_vision] 全部重试失败，无法定位: {target}")
    return None


if __name__ == "__main__":
    # 命令行用途：
    #   python ima_vision.py task    → 打印当前待处理任务
    #   python ima_vision.py answer 1234 567  → 写回坐标 (AI 手动测试用)
    import sys
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]
        if cmd == "task":
            t = read_pending_task()
            if t:
                print(json.dumps(t, ensure_ascii=False, indent=2))
            else:
                print("无待处理任务")
        elif cmd == "answer" and len(sys.argv) >= 4:
            answer_task({"x": int(sys.argv[2]), "y": int(sys.argv[3]),
                         "desc": "手动输入"})
        else:
            print("用法: python ima_vision.py task")
            print("      python ima_vision.py answer <x> <y>")
