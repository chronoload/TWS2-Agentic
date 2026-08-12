from mcp.harness.hooks import CommandGuardHook, HookDecision
from mcp.middleware.base import MiddlewareAction, MiddlewareContext
from mcp.middleware.chain import MiddlewareChain, add_default_middlewares
from mcp.middleware.command_guard import (
    CommandGuardMiddleware,
    analyze_command,
)


def _blocked(command):
    return analyze_command(command).blocked


def test_blocked_write_commands():
    assert _blocked("rm -rf /tmp/foo")
    assert _blocked("rm file.txt")
    assert _blocked("sed -i 's/a/b/g' file.txt")
    assert _blocked("sed -i.bak s/a/b/ file.txt")
    assert _blocked("git commit -m 'init'")
    assert _blocked("git push origin main")
    assert _blocked("echo x > file.txt")
    assert _blocked("echo x >> file.txt")
    assert _blocked("mv a.txt b.txt")
    assert _blocked("mkdir -p newdir")
    assert _blocked("git checkout feature")
    assert _blocked("git stash")
    assert _blocked("sudo rm -rf /")
    assert _blocked("perl -i -pe 's/x/y/' f.txt")
    assert _blocked("ls; rm -rf tmp")


def test_readonly_allowed():
    assert not _blocked("ls -la")
    assert not _blocked("grep -r foo .")
    assert not _blocked("cat file.txt")
    assert not _blocked("git status")
    assert not _blocked("git log --oneline")
    assert not _blocked("git stash list")
    assert not _blocked("git worktree list")
    assert not _blocked("git submodule status")
    assert not _blocked("git --help")
    assert not _blocked("python --version")
    assert not _blocked("env | grep PATH")
    assert not _blocked("head -n 20 file.txt")


def test_quotes_and_comments_not_false_positive():
    assert not _blocked('echo "rm -rf /"')
    assert not _blocked("echo 'git commit -m test'")
    assert not _blocked("# rm -rf /")
    assert not _blocked("echo hello # rm -rf /")
    assert not _blocked('printf "%s" "mv a b"')


def test_safe_redirect_targets_allowed():
    assert not _blocked("ls > /tmp/out.txt")
    assert not _blocked("python x.py 2> /dev/null")
    assert not _blocked("cat file.txt > /dev/null")
    assert not _blocked("git log > /tmp/git.log 2>&1")
    assert not _blocked("grep foo bar 2>&1 | head")


def test_analyze_result_fields():
    result = analyze_command("rm -rf x")
    assert result.blocked is True
    assert result.reason
    assert result.matched_command
    empty = analyze_command("ls")
    assert empty.blocked is False
    assert empty.reason == ""
    assert empty.matched_command == ""


def test_middleware_plan_mode_via_context():
    mw = CommandGuardMiddleware()
    ctx = MiddlewareContext(extra={"mode": "plan"})
    result = mw.before_tool("sandbox_execute", {"command": "rm -rf /tmp/x"}, ctx)
    assert result.action == MiddlewareAction.STOP
    assert "Plan 模式禁止" in result.reason


def test_middleware_plan_mode_via_tool_args():
    mw = CommandGuardMiddleware()
    ctx = MiddlewareContext()
    result = mw.before_tool("bash", {"command": "git commit -m x", "mode": "plan"}, ctx)
    assert result.action == MiddlewareAction.STOP


def test_middleware_set_mode():
    mw = CommandGuardMiddleware()
    mw.set_mode("plan")
    ctx = MiddlewareContext()
    result = mw.before_tool("execute", {"command": "git push"}, ctx)
    assert result.action == MiddlewareAction.STOP


def test_middleware_act_mode_passthrough():
    mw = CommandGuardMiddleware()
    ctx = MiddlewareContext(extra={"mode": "act"})
    result = mw.before_tool("sandbox_execute", {"command": "rm -rf /tmp/x"}, ctx)
    assert result.action != MiddlewareAction.STOP
    result = mw.before_tool("bash", {"command": "git commit -m x", "mode": "act"}, ctx)
    assert result.action != MiddlewareAction.STOP


def test_middleware_mode_getter():
    mw = CommandGuardMiddleware(mode_getter=lambda: "plan")
    ctx = MiddlewareContext()
    result = mw.before_tool("bash", {"command": "rm -rf /tmp/x"}, ctx)
    assert result.action == MiddlewareAction.STOP


def test_middleware_readonly_in_plan_allowed():
    mw = CommandGuardMiddleware()
    mw.set_mode("plan")
    ctx = MiddlewareContext()
    result = mw.before_tool("sandbox_execute", {"command": "git status"}, ctx)
    assert result.action != MiddlewareAction.STOP
    result = mw.before_tool("sandbox_execute", {"command": "ls > /tmp/out.txt"}, ctx)
    assert result.action != MiddlewareAction.STOP


def test_middleware_non_terminal_tool_passthrough():
    mw = CommandGuardMiddleware()
    mw.set_mode("plan")
    ctx = MiddlewareContext()
    result = mw.before_tool("write_file", {"path": "a.txt", "content": "x"}, ctx)
    assert result.action != MiddlewareAction.STOP


def test_command_guard_hook():
    hook = CommandGuardHook(mode_getter=lambda: "plan")
    spec = hook.spec()
    assert spec.name == "command_guard"
    assert spec.event == "pre_tool_use"
    denied = spec.handler("bash", {"command": "rm -rf /tmp/x"})
    assert denied.decision == HookDecision.DENY
    assert "Plan 模式禁止" in denied.reason
    allowed = spec.handler("bash", {"command": "git status"})
    assert allowed.decision == HookDecision.ALLOW


def test_command_guard_hook_act_mode():
    hook = CommandGuardHook(mode_getter=lambda: "act")
    result = hook.spec().handler("bash", {"command": "rm -rf /tmp/x"})
    assert result.decision == HookDecision.ALLOW


def test_add_default_middlewares():
    chain = MiddlewareChain()
    assert add_default_middlewares(chain, mode_getter=lambda: "plan") is True
    names = [mw.name for mw in chain.middlewares]
    assert "command_guard" in names
    mw = next(m for m in chain.middlewares if m.name == "command_guard")
    ctx = MiddlewareContext()
    result = mw.before_tool("bash", {"command": "rm -rf /tmp/x"}, ctx)
    assert result.action == MiddlewareAction.STOP
