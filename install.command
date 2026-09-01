#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================================"
echo "  Roblox Studio MCP Universal Bridge - 1-Click Installer"
echo "============================================================"
echo ""

# Find Python 3
PYTHON_EXE=""
for cmd in python3 python py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            PYTHON_EXE="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_EXE" ]; then
    echo "❌ [ERROR] Python 3.8+ was not found on your system."
    echo "Please install Python 3.8+ from https://www.python.org/ or via 'brew install python3'"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[1/3] Registering roblox-studio-mcp package..."
"$PYTHON_EXE" -m pip install -e . --quiet 2>/dev/null || true

echo "[2/3] Injecting MCP configuration into Claude Desktop, Cursor, OpenCode, Antigravity..."
"$PYTHON_EXE" -m roblox_studio_mcp inject

echo ""
echo "[3/3] Running system diagnostics..."
"$PYTHON_EXE" -m roblox_studio_mcp doctor

echo ""
echo "============================================================"
echo "🎉 Setup complete! You are ready to play."
echo ""
echo "👉 What to do now:"
echo "   1. Open Roblox Studio (File > Beta Features > Model Context Protocol)"
echo "   2. Restart your AI IDE (Claude Desktop, Cursor, Antigravity, etc.)"
echo "============================================================"
echo ""
read -p "Press Enter to finish..."