"""Command Line Interface for Roblox Studio MCP Bridge."""

import argparse
import datetime

from roblox_studio_mcp import __version__
from roblox_studio_mcp.core.bridge import RobloxMCPBridge
from roblox_studio_mcp.core.resolver import RobloxStudioResolver
from roblox_studio_mcp.injector.config_injector import MCPConfigInjector

_IDE_TARGETS = ["all", "claude", "cursor", "opencode", "antigravity"]


def _add_target_arg(subparser):
    subparser.add_argument("--target", choices=_IDE_TARGETS, default="all", help="Target IDE")


def cmd_run(args):
    bridge = RobloxMCPBridge()
    bridge.run()


def cmd_doctor(args):
    print("============================================================")
    print(f"🩺 Roblox Studio MCP Doctor (v{__version__})")
    print("============================================================\n")

    # 1. Resolver Check
    candidates = RobloxStudioResolver.get_all_candidates()
    if candidates:
        print(f"✅ Found {len(candidates)} StudioMCP candidate(s):")
        for i, c in enumerate(candidates):
            mtime_str = datetime.datetime.fromtimestamp(c.last_modified).strftime("%Y-%m-%d %H:%M:%S")
            tag = " ⭐ (ACTIVE / NEWEST)" if i == 0 else ""
            print(f"  [{i + 1}] {c.executable_path}")
            print(f"      Version Dir : {c.version_dir.name}")
            print(f"      Modified    : {mtime_str}")
            print(f"      Studio Beta : {'Yes' if c.has_studio_beta else 'No'}{tag}")
    else:
        print("❌ No StudioMCP.exe found!")
        print("   Please make sure Roblox Studio is installed and has Beta Features -> Model Context Protocol enabled.")

    # 2. Config Targets Check
    print("\n📂 IDE Configuration Targets:")
    targets = MCPConfigInjector.get_target_paths()
    for ide_name, paths in targets.items():
        print(f"  [{ide_name.upper()}]")
        for p in paths:
            exists = p.exists()
            print(f"    {'✅' if exists else '⚪'} {p} ({'Exists' if exists else 'Not created yet'})")

    # 3. Legacy mcp.bat entry check
    print("\n🔍 Checking for Roblox's broken mcp.bat entries...")
    legacy = MCPConfigInjector.find_legacy_entries()
    if legacy:
        print("⚠️  WARNING: Found legacy Roblox mcp.bat entries that will intermittently crash the")
        print("   bridge connection. Roblox Studio re-adds these on every weekly auto-update.")
        for cfg_path, keys in legacy.items():
            print(f"   {cfg_path}: {', '.join(repr(k) for k in keys)}")
        print("\n   Run the following to remove them:")
        print("     python -m roblox_studio_mcp scrub")
    else:
        print("✅ No conflicting Roblox mcp.bat entries found.")

    print("\n✨ Diagnostic check completed.")


def cmd_inject(args):
    print("🚀 Injecting Roblox Studio MCP configuration...")
    files = MCPConfigInjector.inject(target_name=args.target)
    if files:
        for f in files:
            print(f"  ✅ Updated: {f}")
        print(f"\n🎉 Successfully injected into {len(files)} config file(s)!")
        print("👉 Please restart Claude Desktop / Cursor / Antigravity for changes to take effect.")
        print()
        print("⚠️  Note: Roblox Studio re-adds its own broken mcp.bat entry on every weekly")
        print("   auto-update. If the connection starts crashing after a Studio update, run:")
        print("     python -m roblox_studio_mcp scrub")
    else:
        print("⚠️ No config files updated.")


def cmd_scrub(args):
    print("🧹 Scanning for Roblox's broken mcp.bat entries...")
    files = MCPConfigInjector.scrub(target_name=args.target)
    if files:
        for f in files:
            print(f"  ✅ Cleaned: {f}")
        print(f"\n🎉 Removed conflicting entries from {len(files)} config file(s)!")
        print("👉 Please restart your IDE for changes to take effect.")
    else:
        print("✅ No conflicting Roblox mcp.bat entries found — nothing to clean up.")


def cmd_eject(args):
    print("🗑️ Removing Roblox Studio MCP configuration...")
    files = MCPConfigInjector.eject(target_name=args.target)
    if files:
        for f in files:
            print(f"  ✅ Removed from: {f}")
        print(f"\n🎉 Successfully ejected from {len(files)} config file(s)!")
    else:
        print("⚠️ No matching configurations found to remove.")


def main():
    parser = argparse.ArgumentParser(
        prog="roblox-studio-mcp",
        description="Universal Roblox Studio MCP Bridge CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.set_defaults(func=cmd_run)
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("run", help="Run the MCP stdio bridge server (default)").set_defaults(func=cmd_run)

    subparsers.add_parser(
        "doctor", help="Run system diagnostics and verify Roblox Studio MCP status"
    ).set_defaults(func=cmd_doctor)

    inject_parser = subparsers.add_parser(
        "inject", help="Auto-inject config into Claude Desktop, Cursor, OpenCode, Antigravity"
    )
    _add_target_arg(inject_parser)
    inject_parser.set_defaults(func=cmd_inject)

    scrub_parser = subparsers.add_parser(
        "scrub",
        help="Remove Roblox's broken mcp.bat entries from IDE configs (safe to re-run after Studio updates)",
    )
    _add_target_arg(scrub_parser)
    scrub_parser.set_defaults(func=cmd_scrub)

    eject_parser = subparsers.add_parser("eject", help="Remove config from IDEs")
    _add_target_arg(eject_parser)
    eject_parser.set_defaults(func=cmd_eject)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
