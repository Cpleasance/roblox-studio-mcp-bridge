#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================================"
echo "  Roblox Studio MCP Universal Bridge - 1-Click Uninstaller"
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
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[1/1] Removing MCP configuration from Claude Desktop, Cursor, OpenCode, Antigravity..."
"$PYTHON_EXE" -m roblox_studio_mcp eject

echo ""
echo "============================================================"
echo "🗑️  Uninstallation complete!"
echo "The roblox_studio MCP server has been removed from your IDEs."
echo "Please restart your AI IDE for changes to take effect."
echo "============================================================"
echo ""
read -p "Press Enter to finish..."
