<#
.SYNOPSIS
    Roblox Studio MCP Universal Bridge - One-Click PowerShell Installer
#>

# Run from the repository root so "python -m roblox_studio_mcp" resolves
# without requiring an install.
Set-Location $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Roblox Studio MCP Universal Bridge - One-Click Installer" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Check for Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ [ERROR] Python 3.8+ was not found on PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/ and ensure it is added to PATH." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/2] Injecting MCP configuration into Claude Desktop, Cursor, OpenCode..." -ForegroundColor Yellow
python -m roblox_studio_mcp inject

Write-Host "`n[2/2] Running system diagnostics..." -ForegroundColor Yellow
python -m roblox_studio_mcp doctor

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "🎉 Installation complete!" -ForegroundColor Green
Write-Host "Please restart Claude Desktop or Cursor for changes to take effect." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
