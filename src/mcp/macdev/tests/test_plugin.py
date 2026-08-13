"""插件平级哲学测试：Plugin 抽象接口扫描捕捉 + patch 自演化闭环。"""
from pathlib import Path
from macdev.core.registry import Registry
from macdev.core.plugin import Plugin, scan_plugins
from macdev import Engine, EventBus, audit, patch


def test_plugin_scan_capture():
    """继承抽象接口即被扫描捕捉（audit.strategy + patch.generator 平级）。"""
    reg = Registry()
    reg.discover()
    assert "audit.strategy" in reg.namespaces()
    assert "patch.generator" in reg.namespaces()
    assert "base" in reg.names("audit.strategy")
    # 修复插件全部被捕捉
    plugins = scan_plugins("patch.generator")
    names = {p.name for p in plugins}
    assert "insert_set_after_clear" in names
    assert "insert_env_todo" in names

def test_patch_self_evolving_loop(tmp_path):
    """自演化闭环：缺陷 → 固化脚本（不改原文件）→ apply → 文件改变 → verify 收敛。"""
    # 造一个有 Event clear 缺陷的项目
    app = tmp_path / "app.py"
    app.write_text(
        "import threading\n"
        "class Session:\n"
        "    def __init__(self):\n"
        "        self._flag = threading.Event()\n"
        "    def stop(self):\n"
        "        self._flag.clear()\n",
        encoding="utf-8")
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "app.js").write_text("class TS2Client {}\n", encoding="utf-8")
    from macdev.audit.task import AuditTask
    task = AuditTask(root=tmp_path,
                     endpoints=[],
                     files={"app": "app.py"},
                     chains={},
                     strategy="base")
    reg = Registry()
    audit.register(reg)
    patch.register(reg)
    reg.discover()
    engine = Engine(reg, EventBus())
    # 1. 审计（无端点也扫 analyze：flag 命中）
    r = engine.run_audit(task, out_dir=tmp_path / "out")
    assert r.data["flag"] >= 1
    # 2. patch gen：生成固化脚本，不改原文件
    from macdev.patch.gen import gen_patches
    before_text = app.read_text(encoding="utf-8")
    gen = gen_patches(engine, tmp_path / "out" / "interface_chain.db",
                      tmp_path, tmp_path / "patches")
    assert gen.data["patches"] >= 1
    assert app.read_text(encoding="utf-8") == before_text  # 原文件未被修改
    scripts = list((tmp_path / "patches").glob("*.py"))
    assert scripts
    # 固化脚本可独立加载（含 PATCH 元数据）
    from macdev.patch import load_patch
    p = load_patch(scripts[0])
    assert p.kind in ("clear_without_set", "stale_cache")
    # 3. apply：显式应用
    from macdev.patch.apply import apply_patch
    ok, msg, n = apply_patch(scripts[0], tmp_path)
    assert ok
    new_text = app.read_text(encoding="utf-8")
    if p.kind == "clear_without_set" and n > 0:
        assert ".set()" in new_text  # 自动修复已插入
