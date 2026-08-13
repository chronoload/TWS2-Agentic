"""
IMA知识库GUI管理器
提供图形化界面访问和操作IMA知识库
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
from datetime import datetime

# Windows控制台编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 计算Claw根目录路径（当前文件的父目录的父目录的父目录的父目录）
# ima_gui.py在scripts/，需要向上4级
current_file = os.path.abspath(__file__)
claw_root = current_file
for _ in range(4):
    claw_root = os.path.dirname(claw_root)

if claw_root not in sys.path:
    sys.path.insert(0, claw_root)

# 导入path_helper
script_dir = os.path.dirname(current_file)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 导入IMA相关模块
try:
    from path_helper import CLAW_DIR, get_ima_backups_dir
except:
    # 如果导入失败，手动计算路径
    CLAW_DIR = claw_root
    get_ima_backups_dir = lambda: os.path.join(claw_root, 'ima_backups')


class IMAGUI:
    """IMA知识库图形化界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("IMA知识库管理器")
        self.root.geometry("900x600")

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        """创建界面组件"""
        # 标题
        title_frame = ttk.Frame(self.root, padding="10")
        title_frame.pack(fill=tk.X)

        ttk.Label(
            title_frame,
            text="IMA知识库管理器",
            font=("Arial", 16, "bold")
        ).pack()

        ttk.Label(
            title_frame,
            text=f"工作目录: {CLAW_DIR}",
            font=("Arial", 9),
            foreground="gray"
        ).pack()

        # 创建选项卡
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建各个页面
        self.create_search_tab()
        self.create_backup_tab()

        # 底部状态栏
        self.status_bar = ttk.Label(
            self.root,
            text="就绪",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X, padx=10, pady=5)

    def create_search_tab(self):
        """创建搜索页面"""
        search_frame = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(search_frame, text="  知识库搜索  ")

        # 搜索区域
        ttk.Label(search_frame, text="向知识库提问:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        query_frame = ttk.Frame(search_frame)
        query_frame.pack(fill=tk.X, pady=(0, 15))

        self.query_entry = ttk.Entry(query_frame, font=("Arial", 11))
        self.query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(query_frame, text="搜索", command=self.on_search).pack(side=tk.LEFT)

        # 结果显示
        ttk.Label(search_frame, text="搜索结果:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 10))

        self.result_text = scrolledtext.ScrolledText(
            search_frame,
            height=18,
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)

        # 按钮栏
        btn_frame = ttk.Frame(search_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="清空", command=self.clear_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="复制", command=self.copy_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="保存", command=self.save_results).pack(side=tk.LEFT, padx=5)

    def create_backup_tab(self):
        """创建备份页面"""
        backup_frame = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(backup_frame, text="  备份工作流  ")

        # IMA客户端路径
        ttk.Label(backup_frame, text="IMA客户端路径:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        path_frame = ttk.Frame(backup_frame)
        path_frame.pack(fill=tk.X, pady=(0, 15))

        self.ima_path_entry = ttk.Entry(path_frame, font=("Arial", 10))
        self.ima_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(path_frame, text="浏览...", command=self.browse_ima_path).pack(side=tk.LEFT)

        # 备份目录
        ttk.Label(backup_frame, text="备份目录:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 10))

        backup_dir_frame = ttk.Frame(backup_frame)
        backup_dir_frame.pack(fill=tk.X, pady=(0, 15))

        backup_dir_entry = ttk.Entry(backup_dir_frame, font=("Arial", 10))
        backup_dir_entry.insert(0, get_ima_backups_dir())
        backup_dir_entry.config(state='readonly')
        backup_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(backup_dir_frame, text="打开", command=self.open_backup_dir).pack(side=tk.LEFT)

        # 备份模式
        mode_frame = ttk.LabelFrame(backup_frame, text="备份模式", padding="15")
        mode_frame.pack(fill=tk.X, pady=(15, 15))

        self.backup_mode = tk.StringVar(value="auto")
        ttk.Radiobutton(mode_frame, text="自动检测（推荐）", value="auto", variable=self.backup_mode).pack(anchor=tk.W, pady=5)
        ttk.Radiobutton(mode_frame, text="强制使用IMA客户端", value="force", variable=self.backup_mode).pack(anchor=tk.W, pady=5)
        ttk.Radiobutton(mode_frame, text="仅打开IMA客户端", value="open_only", variable=self.backup_mode).pack(anchor=tk.W, pady=5)

        # 操作按钮
        action_frame = ttk.Frame(backup_frame)
        action_frame.pack(fill=tk.X, pady=(15, 0))

        ttk.Button(action_frame, text="开始备份", command=self.on_backup, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="测试连接", command=self.test_connection, width=15).pack(side=tk.LEFT, padx=5)

        # 日志
        ttk.Label(backup_frame, text="操作日志:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 10))

        self.log_text = scrolledtext.ScrolledText(
            backup_frame,
            height=10,
            font=("Consolas", 9),
            state='disabled'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ========== 事件处理 ==========

    def on_search(self):
        """执行搜索"""
        query = self.query_entry.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入搜索问题")
            return

        self.status_bar.config(text="正在搜索...")
        self.root.update()

        # 在新线程中执行
        thread = threading.Thread(target=self._search, args=(query,))
        thread.daemon = True
        thread.start()

    def _search(self, query):
        """搜索线程"""
        try:
            self._append_log(f"搜索: {query}")
            self._append_log(f"时间: {datetime.now().strftime('%H:%M:%S')}")

            # 尝试导入并搜索
            parent_dir = os.path.dirname(script_dir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            from search_ima import YuanQiChat
            client = YuanQiChat()
            response = client.chat(query)
            answer = client.extract_answer(response)

            # 显示结果
            self.root.after(0, lambda: self._show_result(answer))
            self.root.after(0, lambda: self.status_bar.config(text="搜索完成"))
            self._append_log("[OK] 搜索成功")

        except Exception as e:
            error = str(e)
            self.root.after(0, lambda: self._show_result(f"搜索失败: {error}"))
            self.root.after(0, lambda: self.status_bar.config(text="搜索失败"))
            self._append_log(f"[FAIL] {error}")

    def _show_result(self, text):
        """显示搜索结果"""
        self.result_text.config(state='normal')
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)
        self.result_text.config(state='disabled')

    def clear_results(self):
        """清空结果"""
        self.result_text.config(state='normal')
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state='disabled')

    def copy_results(self):
        """复制结果"""
        self.result_text.config(state='normal')
        text = self.result_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.result_text.config(state='disabled')
        messagebox.showinfo("提示", "已复制到剪贴板")

    def save_results(self):
        """保存结果"""
        self.result_text.config(state='normal')
        text = self.result_text.get(1.0, tk.END)
        self.result_text.config(state='disabled')

        if not text.strip():
            messagebox.showwarning("提示", "没有内容可保存")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialdir=get_ima_backups_dir()
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"IMA知识库搜索结果\n")
                    f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"问题: {self.query_entry.get()}\n")
                    f.write("="*80 + "\n\n")
                    f.write(text)
                messagebox.showinfo("提示", "保存成功")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")

    def browse_ima_path(self):
        """浏览IMA客户端"""
        filename = filedialog.askopenfilename(
            title="选择IMA客户端",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if filename:
            self.ima_path_entry.delete(0, tk.END)
            self.ima_path_entry.insert(0, filename)

    def open_backup_dir(self):
        """打开备份目录"""
        os.makedirs(get_ima_backups_dir(), exist_ok=True)
        os.startfile(get_ima_backups_dir())

    def on_backup(self):
        """执行备份"""
        mode = self.backup_mode.get()
        ima_path = self.ima_path_entry.get().strip()

        self.status_bar.config(text="正在执行备份...")
        self.root.update()

        thread = threading.Thread(target=self._backup, args=(mode, ima_path))
        thread.daemon = True
        thread.start()

    def _backup(self, mode, ima_path):
        """备份线程"""
        try:
            self._append_log(f"开始备份工作流")
            self._append_log(f"模式: {mode}")

            # 导入backup_to_ima
            parent_dir = os.path.dirname(script_dir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            from backup_to_ima import IMABackupWorkflow

            workflow = IMABackupWorkflow()
            if ima_path:
                workflow.ima_exe_path = ima_path

            # 执行
            if mode == "force":
                result = workflow.run_backup_workflow(force_ima=True)
            elif mode == "open_only":
                success = workflow.open_ima_client()
                result = {"mode": "open_only", "success": success}
            else:
                result = workflow.run_backup_workflow(force_ima=False)

            # 显示结果
            if result['success']:
                self._append_log(f"[OK] 备份完成: {result['mode']}")
            else:
                self._append_log(f"[FAIL] 备份失败: {result.get('error', '未知')}")

            self.root.after(0, lambda: self.status_bar.config(text="备份完成"))

        except Exception as e:
            self._append_log(f"[FAIL] {e}")
            self.root.after(0, lambda: self.status_bar.config(text="备份失败"))

    def test_connection(self):
        """测试连接"""
        self.status_bar.config(text="正在测试...")
        self.root.update()

        thread = threading.Thread(target=self._test)
        thread.daemon = True
        thread.start()

    def _test(self):
        """测试线程"""
        try:
            parent_dir = os.path.dirname(script_dir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            from backup_to_ima import IMABackupWorkflow
            workflow = IMABackupWorkflow()

            ok = workflow._test_yuanqi_connection()

            if ok:
                self._append_log("[OK] 腾讯元器连接正常")
                self.root.after(0, lambda: self.status_bar.config(text="连接正常"))
                self.root.after(0, lambda: messagebox.showinfo("测试结果", "连接成功"))
            else:
                self._append_log("[INFO] 腾讯元器未配置")
                self.root.after(0, lambda: self.status_bar.config(text="未配置"))
                self.root.after(0, lambda: messagebox.showinfo("测试结果", "未配置API，将使用IMA客户端"))

        except Exception as e:
            self._append_log(f"[FAIL] {e}")
            self.root.after(0, lambda: self.status_bar.config(text="测试失败"))

    def _append_log(self, message):
        """追加日志"""
        self.root.after(0, lambda: self._do_append_log(message))

    def _do_append_log(self, message):
        """实际追加日志"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')


def main():
    root = tk.Tk()
    app = IMAGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
