@echo off
chcp 65001 >nul
echo ====================================
echo   IMA知识库管理器
echo ====================================
echo.
echo 正在启动图形界面...
echo.

python c:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\ima_gui.py

if errorlevel 1 (
    echo.
    echo [错误] 启动失败
    echo.
    pause
)
