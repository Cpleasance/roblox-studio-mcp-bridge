<#
.SYNOPSIS
    Roblox Studio MCP Universal Bridge - One-Click PowerShell Uninstaller
#>

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($RepoRoot) { Set-Location -Path $RepoRoot }

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Roblox Studio MCP Universal Bridge - One-Click Uninstaller" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Check for Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ [ERROR] Python 3.8+ was not found on PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/ and ensure it is added to PATH." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/1] Removing MCP configuration from Claude Desktop, Cursor, OpenCode, Antigravity..." -ForegroundColor Yellow
python -m roblox_studio_mcp eject

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "🗑️  Uninstallation complete!" -ForegroundColor Green
Write-Host "The roblox_studio MCP server has been removed from your IDEs." -ForegroundColor Green
Write-Host "Please restart Claude Desktop or Cursor for changes to take effect." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
