"""Command Line Interface for Roblox Studio MCP Bridge."""

import argparse
import datetime
import os
import sys

from roblox_studio_mcp import __version__
from roblox_studio_mcp.core import batfix
from roblox_studio_mcp.core.bridge import RobloxMCPBridge
from roblox_studio_mcp.core.resolver import RobloxStudioResolver
from roblox_studio_mcp.injector.config_injector import MCPConfigInjector

_IDE_TARGETS = ["all", "claude", "cursor", "opencode", "antigravity"]


def _add_target_arg(subparser):
    subparser.add_argument("--target", choices=_IDE_TARGETS, default="all", help="Target IDE")


def _self_command(mode: str) -> str:
    """How to re-invoke this CLI, matching how it was installed."""
    if mode == "uvx":
        return "uvx roblox-studio-mcp-bridge"
    if mode == "repo":
        return "python -m roblox_studio_mcp"
    return "roblox-studio-mcp"


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

    # 3. Roblox's own (broken) MCP entries
    print("\n🔍 Checking for Roblox's own MCP entries...")
    legacy = MCPConfigInjector.find_legacy_entries()
    if legacy:
        print("⚠️  Found Roblox's own entry (its mcp.bat launcher has a broken multi-line")
        print("   if/else that crashes the connection). Roblox re-adds this on Studio updates.")
        for cfg_path, keys in legacy.items():
            print(f"   {cfg_path}: {', '.join(repr(k) for k in keys)}")
        print("\n   Harmless if the bridge's own 'roblox_studio' entry is also present -")
        print("   it overrides this. To remove the broken entry now:")
        print(f"     {_self_command(MCPConfigInjector.detect_mode())} scrub")
    else:
        print("✅ No conflicting Roblox entries found.")

    # 4. Roblox's mcp.bat launcher script itself
    print("\n🩹 Roblox mcp.bat launcher:")
    status = batfix.launcher_status()
    path = batfix.launcher_path()
    if status == "absent":
        print("   ⚪ Not present (nothing to repair).")
    elif status == "managed":
        print(f"   ✅ Repaired and managed by the bridge: {path}")
    elif status == "broken":
        print(f"   ❌ Present and BROKEN (Roblox's multi-line if/else): {path}")
        print(f"      Fix it with:  {_self_command(MCPConfigInjector.detect_mode())} scrub")
    else:
        print(f"   ✅ Present and currently parses: {path}")
        print("      (still fragile - the bridge replaces it on 'inject' / 'scrub' / startup)")

    print("\n✨ Diagnostic check completed.")


def cmd_inject(args):
    print("🚀 Injecting Roblox Studio MCP configuration...")
    mode = args.mode if args.mode != "auto" else MCPConfigInjector.detect_mode()
    print(f"   Install mode: {mode}")
    files = MCPConfigInjector.inject(target_name=args.target, mode=args.mode)
    if files:
        for f in files:
            print(f"  ✅ Updated: {f}")
        print(f"\n🎉 Successfully injected into {len(files)} config file(s)!")
    else:
        print("⚠️ No config files updated.")

    repaired = batfix.repair_roblox_launchers(strict=True)
    if repaired:
        for f in repaired:
            print(f"  🩹 Repaired Roblox's broken launcher: {f}")

    if files or repaired:
        print("\n👉 Please restart Claude Desktop / Cursor / Antigravity for changes to take effect.")
        print()
        print("⚠️  Note: Roblox Studio re-adds its own broken entry / mcp.bat on every weekly")
        print("   auto-update. The bridge auto-heals both on startup; if problems persist, run:")
        print(f"     {_self_command(mode)} scrub")


def cmd_scrub(args):
    print("🧹 Scanning for Roblox's broken MCP entries...")
    files = MCPConfigInjector.scrub(target_name=args.target)
    for f in files:
        print(f"  ✅ Cleaned: {f}")

    repaired = batfix.repair_roblox_launchers(strict=True)
    for f in repaired:
        print(f"  🩹 Repaired Roblox's broken launcher: {f}")

    if files or repaired:
        print(f"\n🎉 Healed {len(files) + len(repaired)} file(s)!")
        print("👉 Please restart your IDE for changes to take effect.")
    else:
        print("✅ Nothing to clean up — no broken Roblox entries or mcp.bat found.")


def cmd_eject(args):
    print("🗑️ Removing Roblox Studio MCP configuration...")
    files = MCPConfigInjector.eject(target_name=args.target)
    for f in files:
        print(f"  ✅ Removed from: {f}")

    restored = batfix.restore_roblox_launchers(strict=True)
    for f in restored:
        print(f"  ↩️  Restored Roblox's original mcp.bat: {f}")

    if files or restored:
        print(f"\n🎉 Ejected from {len(files) + len(restored)} file(s)!")
    else:
        print("⚠️ No matching configurations found to remove.")


def _force_utf8_stdio() -> None:
    """Emit UTF-8 regardless of the console code page.

    Windows pipes/redirected output default to cp1252, which cannot encode the
    emoji in the CLI banners. Applied here so every entry point (console script,
    ``python -m``, direct import) is covered, not just ``__main__``.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # not a reconfigurable TextIO
            pass


def main():
    _force_utf8_stdio()
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
    inject_parser.add_argument(
        "--mode",
        choices=["auto", "repo", "pip", "uvx"],
        default="auto",
        help="Config entry style: repo (bind to this checkout), pip (installed package), "
        "uvx (no install), or auto (detect). Default: auto.",
    )
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
    try:
        args.func(args)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:  # noqa: BLE001 - top-level: surface everything to the user
        cmd = getattr(args, "command", None) or "run"
        print(f"\n❌ '{cmd}' failed: {type(e).__name__}: {e}", file=sys.stderr)
        if os.environ.get("ROBLOX_STUDIO_MCP_LOG_LEVEL", "").upper() == "DEBUG":
            raise
        print(
            "   Re-run with ROBLOX_STUDIO_MCP_LOG_LEVEL=DEBUG for the full traceback.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
