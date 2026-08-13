@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title TS2_dev 快速启动器
cd /d "%~dp0"

rem ================================================
rem   TS2_dev 快速启动器
rem   用法: 双击运行(交互菜单) 或 start.bat [1|2|3|4]
rem         [1] 课程追踪系统    (run.py)
rem         [2] MCP Agent 助手  (run_mcp_agent.py)
rem         [3] 测试模块导入    (test_imports.py)
rem         [4] 测试 MCP        (test_mcp.py)
rem ================================================

if not "%~1"=="" (
    set "choice=%~1"
    goto :run
)

echo ================================================
echo   TS2_dev 快速启动器
echo ================================================
echo   [1] 课程追踪系统    (run.py)
echo   [2] MCP Agent 助手  (run_mcp_agent.py)
echo   [3] 测试模块导入    (test_imports.py)
echo   [4] 测试 MCP        (test_mcp.py)
echo   [0] 退出
echo ================================================
set /p choice=请选择 [0-4]: 

:run
if "%choice%"=="0" exit /b 0
if "%choice%"=="1" goto :run_main
if "%choice%"=="2" goto :run_mcp
if "%choice%"=="3" goto :run_test_imports
if "%choice%"=="4" goto :run_test_mcp

echo 无效选择，默认启动课程追踪系统
goto :run_main

:run_main
echo.
echo [启动] 课程追踪系统 (run.py) ...
python run.py
goto :end

:run_mcp
echo.
echo [启动] MCP Agent 助手 (run_mcp_agent.py) ...
python run_mcp_agent.py
goto :end

:run_test_imports
echo.
echo [测试] 模块导入 (test_imports.py) ...
python test_imports.py
goto :end

:run_test_mcp
echo.
echo [测试] MCP (test_mcp.py) ...
python test_mcp.py
goto :end

:end
echo.
echo 程序已退出。
pause
