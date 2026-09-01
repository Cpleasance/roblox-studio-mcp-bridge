<#
.SYNOPSIS
    Roblox Studio MCP Universal Bridge - 1-Click PowerShell Installer
#>

Set-Location $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Roblox Studio MCP Universal Bridge - 1-Click Installer" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Locate Python
$pythonExe = $null
foreach ($cmd in @("python", "py", "python3")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        $pythonExe = $cmd
        break
    }
}

if (-not $pythonExe) {
    Write-Host "❌ [ERROR] Python 3.8+ was not found on PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/ and check 'Add Python to PATH'." -ForegroundColor Yellow
    Start-Process "https://www.python.org/downloads/"
    exit 1
}

Write-Host "[1/3] Registering roblox-studio-mcp package..." -ForegroundColor Yellow
& $pythonExe -m pip install -e . --no-warn-script-location --quiet 2>$null

Write-Host "[2/3] Injecting MCP configuration into Claude Desktop, Cursor, OpenCode, Antigravity..." -ForegroundColor Yellow
& $pythonExe -m roblox_studio_mcp inject

Write-Host "`n[3/3] Running system diagnostics..." -ForegroundColor Yellow
& $pythonExe -m roblox_studio_mcp doctor

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "🎉 Setup complete! You are ready to play." -ForegroundColor Green
Write-Host ""
Write-Host "👉 What to do now:" -ForegroundColor Green
Write-Host "   1. Open Roblox Studio (File > Beta Features > Model Context Protocol)" -ForegroundColor White
Write-Host "   2. Restart your AI IDE (Claude Desktop, Cursor, Antigravity, etc.)" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
