import sys
import json
import argparse

from .policy import SandboxPolicy
from .executor import SandboxExecutor, ExecutionResult
from .shell import ShellSession


def _handle_exec(args):
    if args.strict:
        policy = SandboxPolicy.strict()
    else:
        policy = SandboxPolicy(max_execution_time=args.timeout)
    cwd = args.cwd or None
    executor = SandboxExecutor(policy=policy, cwd=cwd)
    result = executor.execute(args.cmd)
    if args.json:
        print(json.dumps({
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.success,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
        }, indent=2))
    else:
        print(result.to_text())
    return result.exit_code


def _handle_script(args):
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error reading file: {exc}", file=sys.stderr)
        return 1
    policy = SandboxPolicy(max_execution_time=args.timeout)
    executor = SandboxExecutor(policy=policy)
    result = executor.execute_script(content, language=args.lang)
    print(result.to_text())
    return result.exit_code


def _handle_shell(args):
    cwd = args.cwd or None
    session = ShellSession(cwd=cwd)
    while True:
        try:
            line = input(f"{session.cwd}> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line.startswith("cd "):
            path = line[3:].strip()
            result = session.cd(path)
            if not result.success:
                print(result.stderr)
            continue
        result = session.run(line)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if not result.success and result.error:
            print(f"Error: {result.error}", file=sys.stderr)


def _handle_policy(args):
    policy = SandboxPolicy()
    print("SandboxPolicy defaults:")
    print(f"  max_execution_time : {policy.max_execution_time}")
    print(f"  max_output_bytes   : {policy.max_output_bytes}")
    print(f"  max_processes      : {policy.max_processes}")
    print(f"  allow_network      : {policy.allow_network}")
    print(f"  allow_file_write   : {policy.allow_file_write}")
    print(f"  allow_file_read    : {policy.allow_file_read}")
    print(f"  allowed_commands   : {sorted(policy.allowed_commands)}")
    print(f"  denied_commands    : {sorted(policy.denied_commands)}")
    print(f"  denied_paths       : {policy.denied_paths}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ws2-sandbox", description="WS2 MCP Sandbox CLI")
    subparsers = parser.add_subparsers(dest="command")

    exec_parser = subparsers.add_parser("exec", help="Execute a command")
    exec_parser.add_argument("cmd", help="Command to execute")
    exec_parser.add_argument("--timeout", type=int, default=30, help="Execution timeout in seconds")
    exec_parser.add_argument("--cwd", default="", help="Working directory")
    exec_parser.add_argument("--json", action="store_true", help="Output as JSON")
    exec_parser.add_argument("--strict", action="store_true", help="Use strict policy")

    script_parser = subparsers.add_parser("script", help="Execute a script file")
    script_parser.add_argument("file", help="Script file path")
    script_parser.add_argument("--lang", default="python", help="Script language (default: python)")
    script_parser.add_argument("--timeout", type=int, default=60, help="Execution timeout in seconds")

    shell_parser = subparsers.add_parser("shell", help="Interactive shell session")
    shell_parser.add_argument("--cwd", default="", help="Working directory")

    subparsers.add_parser("policy", help="Print current SandboxPolicy settings")

    args = parser.parse_args(argv)

    if args.command == "exec":
        return _handle_exec(args)
    elif args.command == "script":
        return _handle_script(args)
    elif args.command == "shell":
        return _handle_shell(args)
    elif args.command == "policy":
        return _handle_policy(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
