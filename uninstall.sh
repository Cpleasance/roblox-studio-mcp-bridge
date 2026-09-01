#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================================"
echo "  Roblox Studio MCP Universal Bridge - Uninstaller"
echo "============================================================"
echo ""

PYTHON_EXE=""
for cmd in python3 python py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON_EXE="$cmd"
        break
    fi
done

if [ -n "$PYTHON_EXE" ]; then
    "$PYTHON_EXE" -m roblox_studio_mcp eject
fi

echo ""
echo "============================================================"
echo "🗑️  Uninstallation complete!"
echo "============================================================"
echo ""