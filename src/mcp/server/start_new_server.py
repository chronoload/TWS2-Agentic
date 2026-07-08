from pathlib import Path
import sys, os, socket, subprocess, time

_ws = str(Path(__file__).resolve().parent.parent.parent.parent)
sys.path.insert(0, _ws)

port = 6907

# kill existing process on port
try:
    r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            pid = line.strip().split()[-1]
            os.system(f"taskkill /F /PID {pid} >nul 2>&1")
            time.sleep(0.5)
except: pass

from mcp.server.app import run_server
os.chdir(_ws)
run_server(workspace_dir=_ws, host="0.0.0.0", port=port, open_browser=False, auto_port=False)
