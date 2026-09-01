@echo off
setlocal enabledelayedexpansion

rem Run from the repository root so "python -m roblox_studio_mcp" resolves
rem without requiring an install.
cd /d "%~dp0"

echo ============================================================
echo   Roblox Studio MCP Universal Bridge - One-Click Uninstaller
echo ============================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.8+ was not found on PATH.
    echo Please install Python from https://www.python.org/ and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/1] Removing MCP configuration from Claude Desktop, Cursor, OpenCode, Antigravity...
python -m roblox_studio_mcp eject

echo.
echo ============================================================
echo 🗑️  Uninstallation complete!
echo The roblox_studio MCP server has been removed from your IDEs.
echo Please restart Claude Desktop or Cursor for changes to take effect.
echo ============================================================
pause
