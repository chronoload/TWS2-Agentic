#!/usr/bin/env bash
# ================================================
#   TS2_dev 快速启动器 (Linux/macOS)
#   用法: ./start.sh          # 交互式菜单
#         ./start.sh 1        # 直接启动课程追踪系统
#         ./start.sh 2        # 直接启动 MCP Agent
#         ./start.sh 3        # 测试模块导入
#         ./start.sh 4        # 测试 MCP
# ================================================

cd "$(dirname "$0")" || exit 1

run_main() {
    echo ""
    echo "[启动] 课程追踪系统 (run.py) ..."
    python3 run.py
}

run_mcp() {
    echo ""
    echo "[启动] MCP Agent 助手 (run_mcp_agent.py) ..."
    python3 run_mcp_agent.py
}

run_test_imports() {
    echo ""
    echo "[测试] 模块导入 (test_imports.py) ..."
    python3 test_imports.py
}

run_test_mcp() {
    echo ""
    echo "[测试] MCP (test_mcp.py) ..."
    python3 test_mcp.py
}

# 带参数直接启动
if [ $# -ge 1 ]; then
    case "$1" in
        1) run_main ;;
        2) run_mcp ;;
        3) run_test_imports ;;
        4) run_test_mcp ;;
        *) echo "用法: $0 [1|2|3|4]"; exit 1 ;;
    esac
    exit 0
fi

# 交互式菜单
echo "================================================"
echo "   TS2_dev 快速启动器"
echo "================================================"
echo "   [1] 课程追踪系统    (run.py)"
echo "   [2] MCP Agent 助手  (run_mcp_agent.py)"
echo "   [3] 测试模块导入    (test_imports.py)"
echo "   [4] 测试 MCP        (test_mcp.py)"
echo "   [0] 退出"
echo "================================================"

read -rp "请选择 [0-4]: " choice

case "$choice" in
    1) run_main ;;
    2) run_mcp ;;
    3) run_test_imports ;;
    4) run_test_mcp ;;
    0) exit 0 ;;
    *) echo "无效选择，默认启动课程追踪系统"; run_main ;;
esac
