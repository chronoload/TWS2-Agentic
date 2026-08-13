@echo off
chcp 65001 >nul
echo ====================================
echo      IMA 宏工作流
echo ====================================
echo.

echo 正在启动IMA备份工作流...
echo.

python c:\Users\qu\WorkBuddy\Claw\.codebuddy\skills\ima-knowledge-base\scripts\ima_macro_workflow.py %*

if errorlevel 1 (
    echo.
    echo [错误] 工作流执行失败
    echo.
    pause
)
