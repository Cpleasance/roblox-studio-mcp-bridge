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
  `list_roblox_studios`, binds one with `set_active_studio`, and transparently
  rebinds and retries (up to 3 attempts with backoff) when a disconnect is
  detected.
- **Multi-IDE config injector** — `inject` / `eject` subcommands with
  `--target all|claude|cursor|opencode|antigravity`. Writes a `command` /
  `args` / `cwd` / `env` (`PYTHONPATH`, `PYTHONIOENCODING`, `PYTHONUNBUFFERED`)
  entry that points at the cloned repo, so no `pip install` is required. Backs
  up every file it touches (`*.backup.json`, `*.corrupt.bak`) and preserves
  unrelated servers.
- **`doctor` diagnostics** — lists every `StudioMCP` candidate (marking the one
  that would be used) and every IDE config path with its existence status.
- **Windows one-click installers** — `install.bat` and `install.ps1`.
- **pytest suite** — 89 tests covering the resolver, protocol, process manager,
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

### Changed

- All diagnostic output goes to **stderr**; `stdout` carries only the JSON-RPC
  message stream. Verbosity is controlled by `ROBLOX_STUDIO_MCP_LOG_LEVEL`
  (default `WARNING`).
- Removed the unused `discovery.py` module.

[Unreleased]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/Cpleasance/roblox-studio-mcp-bridge/releases/tag/v1.2.0
