import os

from src.mcp.server.app import run_server


if __name__ == "__main__":
    # 部署平台（Hugging Face Spaces / Render）通过 $PORT 注入端口；
    # 本地回退到 TS2_PORT 或默认 6906。
    port = int(os.environ.get("PORT", os.environ.get("TS2_PORT", "6906")))
    # TS2_WORKSPACE 不设置时，app 默认用 cwd（容器里即 /app，落在平台持久卷上）
    workspace = os.environ.get("TS2_WORKSPACE")
    run_server(
        workspace_dir=workspace,
        host="0.0.0.0",
        port=port,
        open_browser=False,   # 服务端无界面，禁止自动开浏览器
        auto_port=True,
    )
