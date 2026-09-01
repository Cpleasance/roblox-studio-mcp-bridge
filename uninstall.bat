@echo off
setlocal enabledelayedexpansion

title Roblox Studio MCP Universal Bridge Uninstaller
cd /d "%~dp0"

echo ============================================================
echo   Roblox Studio MCP Universal Bridge - 1-Click Uninstaller
echo ============================================================
echo.

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
    echo [ERROR] Python was not found on PATH.
    pause
    exit /b 1
)

echo [1/1] Removing MCP configuration from Claude Desktop, Cursor, OpenCode, Antigravity...
%PYTHON_EXE% -m roblox_studio_mcp eject

echo.
echo ============================================================
echo 🗑️  Uninstallation complete!
echo The roblox_studio MCP server has been removed from your IDEs.
echo Please restart your AI IDE for changes to take effect.
echo ============================================================
pause
