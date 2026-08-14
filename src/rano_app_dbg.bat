@echo off
rem ============================================================
rem  rano_app_dbg.bat - TS2 多服务调试启动器（Windows 包装）
rem
rem  双击运行 = 交互模式启动 TS2（Ctrl+C 停止）
rem  传参透传：--no-browser / --json / --host 等
rem    rano_app_dbg.bat --json         机器模式，输出结构化状态
rem    rano_app_dbg.bat --no-browser   不开浏览器
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python rano_app_dbg.py %*
    goto :end
)
where py >nul 2>nul
if %errorlevel%==0 (
    py rano_app_dbg.py %*
    goto :end
)
echo [ERROR] 未找到 python，请安装 Python 并加入 PATH
pause

:end
