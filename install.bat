@echo off
setlocal enabledelayedexpansion

rem Run from the repository root so "python -m roblox_studio_mcp" resolves
rem without requiring an install.
cd /d "%~dp0"

echo ============================================================
echo   Roblox Studio MCP Universal Bridge - One-Click Installer
echo ============================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.8+ was not found on PATH.
    echo Please install Python from https://www.python.org/ and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/2] Injecting MCP configuration into Claude Desktop, Cursor, OpenCode...
python -m roblox_studio_mcp inject

echo.
echo [2/2] Running system diagnostics...
python -m roblox_studio_mcp doctor

echo.
echo ============================================================
echo 🎉 Installation complete!
echo Please restart Claude Desktop or Cursor to begin.
echo ============================================================
pause
