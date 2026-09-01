# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes yet._

## [1.3.0] - 2026-09-01

### Added

- **PyPI distribution** — the bridge is now installable as `pip install roblox-studio-mcp`
  or `uvx roblox-studio-mcp`, in addition to the source-checkout flow.
- **`inject --mode auto|repo|pip|uvx`** — `inject` detects whether it is running
  from a source checkout or an installed package and writes the matching
  `mcpServers.roblox_studio` entry: `repo` keeps the `cwd` + `PYTHONPATH` binding
  to the clone, `pip` / `uvx` drop it entirely (no move sensitivity). Override with
  `--mode`. Exposed as `MCPConfigInjector.detect_mode()` /
  `MCPConfigInjector.build_bridge_entry()`.

### Changed

- **Consolidated installer scripts** — reduced to one double-clickable installer and
  uninstaller per supported OS: `install.bat` / `uninstall.bat` (Windows) and
  `install.command` / `uninstall.command` (macOS). Removed the redundant `.ps1`
  variants (PowerShell blocks double-clicked scripts by default; `.bat` always runs)
  and the `.sh` variants (identical to the `.command` files). Added the previously
  missing `uninstall.command`. The manual `python -m roblox_studio_mcp inject` /
  `eject` path is unchanged and still covers Linux and locked-down shells.
- **README** — quick start moved to the top of the file; the rest of the content is
  unchanged, only reordered below it.
- **Repository layout** — `CONTRIBUTING.md` and `SECURITY.md` moved into `.github/`
  (GitHub still surfaces both in the same places).

### Internal

_No behavioural change — CLI, protocol handling, and resolver results are identical._

- `core/bridge.py`: the `_dispatch` if/elif ladder is now a method-name → handler
  table (`_HANDLERS`), with `_forward_unknown` / `_server_info` extracted. A
  non-string `method` (spec-violating input) still routes exactly as before.
- `core/resolver.py`: the duplicated root-dir / `version-*` scan blocks are folded
  into `_candidate_at()`, plus a `_resolve()` helper for best-effort `Path.resolve`.
- `injector/config_injector.py`: `scrub` / `find_legacy_entries` / `eject` share a
  single `_iter_config_servers()` walk and a `_legacy_keys()` matcher.
- `cli.py`: fixes a `ruff` line-length failure and switches subcommand routing to
  `argparse` `set_defaults(func=...)`.

### Tests

Suite grown from 118 to 152 tests. New coverage:

- **Refactor branches** — the `_HANDLERS` `tools/call` route, the id-less
  unknown-notification drop, `resolver._candidate_at` executable de-duplication,
  and the shared `_iter_config_servers` skips for non-dict `mcpServers` / non-object
  JSON roots.
- **Non-string `method`** — a spec-violating array/object `method` is forwarded /
  answered `METHOD_NOT_FOUND` (with an id) or dropped (without), never raised.
- **`inject --mode`** — `repo` / `pip` / `uvx` entry shapes, `auto` detection, and
  rejection of an unknown mode.
- **macOS / Linux path branches** — `get_target_paths()` and the resolver's
  platform search-root list are now exercised on any host via `sys.platform`
  stubbing (`config_injector.py` 89% → 100%, `resolver.py` → 100%). The two native
  `skipif` tests are kept as on-OS smoke checks.
- **Startup failure** — `run()` turns a missing `StudioMCP` binary or a failed
  spawn into the stderr hint + `exit(1)`, not a traceback.
- **Handler exceptions** — a handler raising mid-request still yields `-32603` for
  a request with an id, stays silent for a notification, and does not desync the
  stdio stream.
- **`_resolve()` fallback** — degrades to the input path on `OSError` /
  `RuntimeError` and discovery survives it.
- **`tests/test_process.py`** (new) — `send_request` early-returns `None` when the
  child is absent or exited, and `_release_pending()` wakes a blocked caller on
  child death (deterministic threaded test).

Coverage: `bridge.py` 83% → 92%, `resolver.py` → 100%, `config_injector.py` → 100%,
`process.py` 33% → 49%.

## [1.2.1] - 2026-09-01

### Added

- **1-Click Click-and-Play Installers** — double-clickable installers for Windows
  (`install.bat`, `install.ps1`) and macOS (`install.command`, `install.sh`).
  Includes smart multi-strategy Python detection (`python`, `py -3`, `python3`),
  automatic package registration (`pip install -e .`), multi-IDE config injection,
  and diagnostic validation in a single click.
- **1-Click Uninstallers** — `uninstall.bat` and `uninstall.sh` for clean removal
  across all supported IDEs.
- **Automatic Self-Healing on Startup** — `RobloxMCPBridge.run()` now automatically
  calls `scrub()` before initializing. Any conflicting `mcp.bat` launchers
  re-added by weekly Roblox Studio updates are silently purged on startup,
  guaranteeing a clean connection without requiring manual user intervention.
- **`scrub` CLI command** (`python -m roblox_studio_mcp scrub`) — dedicated command
  to scan and remove broken legacy `mcp.bat` launcher entries from all IDE configs
  without touching the bridge or unrelated MCP servers.
- **`doctor` legacy entry detection** — diagnostic check now actively scans for
  conflicting `mcp.bat` entries and suggests the remediation command.

### Fixed

- **Antigravity config location** — corrected primary config target path to
  `~/.gemini/antigravity/mcp_config.json` across Windows, macOS, and Linux
  (previously wrote to `~/.antigravity/mcp_config.json` which Antigravity did not read).
  Legacy paths are preserved as fallbacks for forks.
- **Target path filtering** — `inject()` now only writes to config files that
  already exist on the machine (or creates the primary path when none exist),
  preventing ghost config files from being created in unused fallback locations.
- **Targeted startup error hints** — when StudioMCP's initialize handshake fails,
  `bridge.py` inspects `stderr_log` for the `expect initialized request` signature
  and outputs a targeted hint explaining the `mcp.bat` race condition.
- **Dynamic package versioning** — `bridge.py` now references `__version__` dynamically
  rather than hardcoding static version strings.

## [1.2.0] - 2026-09-01

First public release of the Universal Roblox Studio MCP Bridge: a pure-Python,
standard-library-only stdio JSON-RPC 2.0 proxy between AI IDE hosts (Claude
Desktop, Cursor, Claude Code, Antigravity, OpenCode, Windsurf) and Roblox
Studio's native `StudioMCP` daemon. Supports Windows and macOS on Python 3.8+.

### Added

- **stdio bridge server** (`python -m roblox_studio_mcp run`) that multiplexes
  host requests onto a single `StudioMCP` child process, virtualizing request
  ids to avoid collisions.
- **`server/discover` handling** — the probe is answered locally by proxying
  `tools/list`, so it never reaches the daemon before `initialize`.
- **Async pipe drainers** — dedicated daemon threads continuously read the
  child's `stdout` and `stderr`; `stderr` is buffered in a bounded in-memory
  ring buffer, eliminating the OS pipe-buffer deadlock.
- **Newest-build executable resolver** — scans all known Roblox install roots,
  prefers the version folder that also contains the Studio Beta binary, and
  breaks ties by newest modification time. Overridable via
  `ROBLOX_STUDIO_MCP_PATH` / `STUDIO_MCP_PATH`.
- **Self-healing session manager** — auto-discovers Studio instances with
  `list_roblox_studios`, caches the `studio_id` and injects it into each
  forwarded tool call, and transparently re-resolves and retries (up to 3
  attempts with backoff) when a disconnect or stale id is detected. Verified
  end-to-end against a live Studio place (`execute_luau`, `get_studio_state`,
  `search_game_tree`, instance creation/cleanup).
- **Multi-IDE config injector** — `inject` / `eject` subcommands with
  `--target all|claude|cursor|opencode|antigravity`. Writes a `command` /
  `args` / `cwd` / `env` (`PYTHONPATH`, `PYTHONIOENCODING`, `PYTHONUNBUFFERED`)
  entry that points at the cloned repo, so no `pip install` is required. Backs
  up every file it touches (`*.backup.json`, `*.corrupt.bak`) and preserves
  unrelated servers.
- **`doctor` diagnostics** — lists every `StudioMCP` candidate (marking the one
  that would be used) and every IDE config path with its existence status.
- **Windows one-click installers** — `install.bat` and `install.ps1`.
- **pytest suite** — 105 tests covering the resolver, protocol, process manager,
  session manager, bridge event loop, and config injector.

### Fixed

- Failed requests now return a proper JSON-RPC `-32603` (internal error)
  response instead of silently leaving the host waiting on an id it will never
  receive.
- A missing `StudioMCP` executable now exits cleanly with a remediation message
  on stderr instead of raising an unhandled traceback.
- Concurrent writes to the child process's `stdin` are serialized with a lock,
  preventing interleaved / corrupted JSON-RPC lines.
- Signal-handler installation is guarded: it is skipped off the main thread and
  each of `SIGINT` / `SIGTERM` / `SIGBREAK` is installed independently so a
  platform that lacks one does not break the others.
- `tools/list` / `server/discover` no longer race StudioMCP's internal
  "waiting for tools" timeout (which runs ~8-10s while no Studio is connected);
  the bridge now waits long enough to capture the daemon's real answer.
- Server-initiated notifications from StudioMCP (`notifications/tools/list_changed`
  and the `resources` / `prompts` variants) are now relayed to the host, so a
  host that listed tools before Studio was open is told to re-list once Studio
  connects. Previously all id-less messages from the daemon were dropped.
- The session manager no longer calls the removed `set_active_studio` tool
  (current StudioMCP builds reject it with "Tool not found", which surfaced in
  Studio's logs and left tool calls without a target). It now passes the
  resolved `studio_id` as a per-call argument, matching the current protocol.
- `inject` now detects and removes a conflicting legacy MCP server entry -
  under any key name - that shells out to Roblox's own broken
  `%LOCALAPPDATA%\Roblox\mcp.bat` launcher (Roblox Studio / its installer
  writes this directly into IDE configs, commonly as `Roblox_Studio`,
  independent of this bridge). Left in place it intermittently wins the race
  against our entry and reproduces exactly the two bugs this bridge fixes: a
  `server/discover`-before-`initialize` panic and cmd.exe `'else' is not
  recognized as an internal or external command` from the batch file's broken
  multi-line `if/else`. Re-running `inject` now cleans it up automatically.

### Changed

- All diagnostic output goes to **stderr**; `stdout` carries only the JSON-RPC
  message stream. Verbosity is controlled by `ROBLOX_STUDIO_MCP_LOG_LEVEL`
  (default `WARNING`).
- Removed the unused `discovery.py` module.
- `inject`/`eject --target antigravity` now write both plausible config
  locations (the Windsurf-lineage `~/.antigravity/mcp_config.json` and the
  Code-OSS-style per-user `.../Antigravity/User/mcp.json`), since Antigravity's
  real config path isn't publicly documented and reports vary by build.

[Unreleased]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/releases/tag/v1.2.0
