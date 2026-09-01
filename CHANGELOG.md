# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes yet._

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

[Unreleased]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/releases/tag/v1.2.0
