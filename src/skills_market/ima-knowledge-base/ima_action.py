"""
ima_action.py
=============
IMA 自动化工厂模式核心模块。

架构：
  IMAAction（抽象基类）
      每个动作的完整生命周期：
        1. bring_to_front()  把 IMA 拉到前台
        2. screenshot()      截图当前屏幕
        3. analyze()         AI 分析截图，返回坐标/状态
        4. execute()         根据分析结果执行操作
        5. verify()          截图确认操作结果，写日志

  IMAActionFactory
      create(action_type, **kwargs) → IMAAction 子类实例

  IMAWorkflow
      run([action1, action2, ...]) → 串联执行，逐步打印进度

调用示例：
  from ima_action import IMAActionFactory, IMAWorkflow

  wf = IMAWorkflow()
  wf.run([
      IMAActionFactory.create("focus"),
      IMAActionFactory.create("upload", file_path=r"C:\\...\\test.pdf"),
      IMAActionFactory.create("search", keyword="test"),
  ])
"""

from __future__ import annotations

import abc
import datetime
import json
import os
import sys
import time
import uuid

# ── 后台预执行保护 ─────────────────────────────────────────────────────────────
# visible_runner 先后台跑一次（isatty=False），pyautogui 操作只在真实终端里执行。
if not sys.stdout.isatty():
    sys.exit(0)

import pyautogui
import pyperclip

# ── 路径 ──────────────────────────────────────────────────────────────────────
CLAW_DIR  = r"C:\Users\qu\WorkBuddy\Claw"
SKILL_DIR = os.path.join(CLAW_DIR, r".codebuddy\skills\ima-knowledge-base")
SHOT_DIR  = os.path.join(CLAW_DIR, "debug_screenshots")
TASK_FILE = os.path.join(CLAW_DIR, "vision_task.json")
RESULT_FILE = os.path.join(CLAW_DIR, "vision_result.json")

os.makedirs(SHOT_DIR, exist_ok=True)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.25


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]


def _log(action_name: str, msg: str):
    print(f"[{action_name}] {msg}", flush=True)


def _take_screenshot(label: str) -> str:
    """截全屏，返回保存路径"""
    fname = f"{label}_{_ts()}.png"
    path  = os.path.join(SHOT_DIR, fname)
    pyautogui.screenshot(path)
    return path


def _get_window() -> dict:
    """探测 IMA 窗口，返回 {hwnd, left, top, right, bottom, width, height}"""
    try:
        import win32gui
        results = []

        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            t = win32gui.GetWindowText(hwnd)
            if any(k in t.lower() for k in ("ima", "知识库", "copilot")):
                r = win32gui.GetWindowRect(hwnd)
                w, h = r[2] - r[0], r[3] - r[1]
                if w > 400 and h > 400:
                    results.append((hwnd, t, r))

        win32gui.EnumWindows(_cb, None)
        if results:
            hwnd, title, r = results[0]
            return dict(hwnd=hwnd, left=r[0], top=r[1],
                        right=r[2], bottom=r[3],
                        width=r[2]-r[0], height=r[3]-r[1],
                        title=title)
    except Exception as e:
        print(f"[window] 探测失败: {e}", flush=True)
    # 兜底：使用上次已知坐标
    return dict(hwnd=None, left=891, top=0, right=2569, bottom=1537,
                width=1678, height=1537, title="IMA(fallback)")


def _bring_to_front(win: dict) -> bool:
    """把 IMA 窗口强制拉到前台，远程操作必须"""
    hwnd = win.get("hwnd")
    if not hwnd:
        print("[window] 无 hwnd，跳过前置", flush=True)
        return False
    try:
        import win32gui, win32con, win32api
        # 若最小化先还原
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        # 模拟 Alt 键绕过前台限制
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.6)
        print(f"[window] IMA 已前置 hwnd={hwnd}", flush=True)
        return True
    except Exception as e:
        print(f"[window] 前置失败: {e}", flush=True)
        return False


def _abs(win: dict, rx: float, ry: float) -> tuple[int, int]:
    """相对比例坐标 → 屏幕绝对坐标"""
    x = win["left"] + int(win["width"]  * rx)
    y = win["top"]  + int(win["height"] * ry)
    return x, y


# ── 硬编码兜底坐标（相对比例，基于 left=891 / 1678×1537 窗口） ───────────────
_FALLBACK_REL = {
    "标题栏":     (0.50,  0.02),
    "知识库灯泡": (0.024, 0.15),
    "上传按钮":   (0.024, 0.22),
    "搜索按钮":   (0.940, 0.055),
    "下载按钮":   (0.960, 0.055),
    "第一个卡片": (0.18,  0.28),
}


# ══════════════════════════════════════════════════════════════════════════════
# 视觉感知：截图 → 写任务 → 等 AI 写回坐标
# ══════════════════════════════════════════════════════════════════════════════

def ask_ai(target: str, hint: str, screenshot_path: str,
           timeout: int = 120) -> tuple[int, int] | None:
    """
    把截图路径+任务描述写入 vision_task.json，
    轮询等待 WorkBuddy AI 把坐标写回 vision_result.json。
    返回 (x, y) 或 None（超时/失败）。
    """
    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":          task_id,
        "screenshot":  screenshot_path,
        "target":      target,
        "hint":        hint,
        "status":      "pending",
        "created_at":  _ts(),
    }
    with open(TASK_FILE, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    print(f"[vision] 等待 AI 分析: {target}  (task_id={task_id})", flush=True)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        if not os.path.exists(RESULT_FILE):
            continue
        try:
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                res = json.load(f)
            if res.get("id") == task_id and res.get("status") == "done":
                x, y = res.get("x"), res.get("y")
                if x is not None and y is not None:
                    print(f"[vision] AI 返回坐标: ({x}, {y})", flush=True)
                    # 清理
                    for fp in (TASK_FILE, RESULT_FILE):
                        try: os.remove(fp)
                        except OSError: pass
                    return int(x), int(y)
        except (json.JSONDecodeError, IOError):
            continue

    print(f"[vision] 超时 ({timeout}s)，AI 未响应", flush=True)
    for fp in (TASK_FILE, RESULT_FILE):
        try: os.remove(fp)
        except OSError: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 抽象基类
# ══════════════════════════════════════════════════════════════════════════════

class IMAAction(abc.ABC):
    """
    每个 IMA 操作的模板：
      run() = bring_to_front → screenshot → analyze → execute → verify
    子类只需实现 _target / _hint / _execute(x, y, win) / _fallback_key。
    """

    # ── 子类须声明 ────────────────────────────────────────────────────────────
    name:         str = "action"       # 动作名，用于日志和截图文件名
    _target:      str = ""             # 传给 AI 的按钮描述
    _hint:        str = ""             # 传给 AI 的界面背景提示
    _fallback_key: str = ""            # 兜底坐标表的键名

    def __init__(self, ai_timeout: int = 90):
        self.ai_timeout = ai_timeout
        self._win: dict = {}

    # ── 模板方法（不可覆盖） ──────────────────────────────────────────────────
    def run(self) -> bool:
        _log(self.name, "── 开始 ──────────────────────")

        # 1. 探测窗口
        self._win = _get_window()
        _log(self.name, f"窗口: {self._win.get('title')} "
                        f"({self._win['width']}x{self._win['height']})")

        # 2. 拉到前台
        _bring_to_front(self._win)

        # 3. 截图
        shot = _take_screenshot(f"before_{self.name}")
        _log(self.name, f"截图: {shot}")

        # 4. AI 分析坐标
        coords = None
        if self._target:
            coords = ask_ai(self._target, self._hint, shot, self.ai_timeout)

        # 5. 兜底坐标
        if coords is None and self._fallback_key:
            rel = _FALLBACK_REL.get(self._fallback_key)
            if rel:
                coords = _abs(self._win, *rel)
                _log(self.name, f"使用兜底坐标 [{self._fallback_key}]: {coords}")

        # 6. 执行
        ok = self._execute(coords, self._win)

        # 7. 截图确认
        time.sleep(0.8)
        verify_shot = _take_screenshot(f"after_{self.name}")
        _log(self.name, f"完成截图: {verify_shot}")
        _log(self.name, f"── {'成功' if ok else '失败'} ──────────────────────")
        return ok

    # ── 子类实现 ──────────────────────────────────────────────────────────────
    @abc.abstractmethod
    def _execute(self, coords: tuple[int, int] | None, win: dict) -> bool:
        """
        拿到坐标后执行具体操作。
        coords: (x, y) 屏幕绝对坐标，或 None（AI+兜底均失败）
        win:    当前窗口信息字典
        返回 True=成功，False=失败
        """
        ...


# ══════════════════════════════════════════════════════════════════════════════
# 工厂
# ══════════════════════════════════════════════════════════════════════════════

class IMAActionFactory:
    """
    用法：
      action = IMAActionFactory.create("upload", file_path="C:/xxx.pdf")
      action = IMAActionFactory.create("search", keyword="论文")
      action = IMAActionFactory.create("download", save_dir="C:/downloads")
    """

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, action_class: type):
        cls._registry[name] = action_class

    @classmethod
    def create(cls, name: str, **kwargs) -> "IMAAction":
        if name not in cls._registry:
            raise ValueError(f"未知 action: {name}。已注册: {list(cls._registry)}")
        return cls._registry[name](**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# 工作流引擎
# ══════════════════════════════════════════════════════════════════════════════

class IMAWorkflow:
    """
    串联执行多个 IMAAction，逐步打印进度。

    用法：
      wf = IMAWorkflow(stop_on_failure=True)
      wf.run([
          IMAActionFactory.create("focus"),
          IMAActionFactory.create("upload", file_path="..."),
          IMAActionFactory.create("search", keyword="..."),
      ])
    """

    def __init__(self, stop_on_failure: bool = True):
        self.stop_on_failure = stop_on_failure

    def run(self, actions: list[IMAAction]) -> dict:
        bar   = "=" * 60
        total = len(actions)
        results = []

        print(f"\n{bar}")
        print(f"  IMA Workflow  共 {total} 步")
        print(bar)

        for i, action in enumerate(actions, 1):
            print(f"\n[{i}/{total}] {action.name}")
            try:
                ok = action.run()
            except Exception as e:
                import traceback
                _log(action.name, f"异常: {e}")
                traceback.print_exc()
                ok = False

            results.append((action.name, ok))

            if not ok and self.stop_on_failure:
                print(f"\n[Workflow] 步骤 [{action.name}] 失败，已停止。")
                break

        # 汇总
        print(f"\n{bar}")
        passed = sum(1 for _, s in results if s)
        print(f"  结果: {passed}/{len(results)} 步成功")
        for name, ok in results:
            mark = "PASS" if ok else "FAIL"
            print(f"    [{mark}] {name}")
        print(bar)

        return {"results": results, "passed": passed, "total": len(results)}
