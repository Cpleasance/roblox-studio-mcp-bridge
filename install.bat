@echo off
setlocal enabledelayedexpansion

title Roblox Studio MCP Universal Bridge Installer
cd /d "%~dp0"

echo ============================================================
echo   Roblox Studio MCP Universal Bridge - 1-Click Installer
echo ============================================================
echo.

rem Locate Python executable (check python, py, python3, or default paths)
set "PYTHON_EXE="

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py -3"
    ) else (
        where python3 >nul 2>nul
        if %ERRORLEVEL% equ 0 (
            set "PYTHON_EXE=python3"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python 3.8+ was not found on your system PATH.
    echo.
    echo Please install Python from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    echo Press any key to open the Python download page...
    pause >nul
    start https://www.python.org/downloads/
    exit /b 1
)

echo [1/3] Registering roblox-studio-mcp package...
%PYTHON_EXE% -m pip install -e . --no-warn-script-location --quiet >nul 2>nul

echo [2/3] Injecting MCP config into Claude Desktop, Cursor, OpenCode, Antigravity...
%PYTHON_EXE% -m roblox_studio_mcp inject

echo.
echo [3/3] Running system diagnostics...
%PYTHON_EXE% -m roblox_studio_mcp doctor

echo.
echo ============================================================
echo 🎉 Setup complete! You are ready to play.
echo.
echo 👉 What to do now:
echo    1. Open Roblox Studio (File ^> Beta Features ^> Model Context Protocol)
echo    2. Restart your AI IDE (Claude Desktop, Cursor, Antigravity, etc.)
echo ============================================================
echo.
pause
