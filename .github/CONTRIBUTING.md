# Contributing

Thanks for your interest in improving the Universal Roblox Studio MCP Bridge.
This is a small, single-purpose project, so the guidelines are short.

## Development setup

```bash
git clone https://github.com/Cpleasance/roblox-studio-mcp-bridge
cd roblox-studio-mcp-bridge
pip install -e ".[dev]"
```

The `[dev]` extra installs `pytest` and `ruff`. The **runtime** package itself
has no dependencies and must keep it that way.

## Running the tests

```bash
python -m pytest
```

The suite (105 tests) uses fakes for the subprocess and filesystem, so it does
not require Roblox Studio to be installed and is safe to run anywhere. Please
add or update tests for any behavior change and keep the suite green.

## Lint and formatting

```bash
ruff check .
ruff format .
```

CI runs both; `ruff format --check .` must pass. Run them before opening a PR.

## Coding conventions

- **Standard library only at runtime.** Do not add third-party imports to
  anything under `roblox_studio_mcp/`. Test-only and dev-only dependencies are
  fine.
- **Python 3.8 compatible.** No `match` statements, no `X | Y` union syntax
  (PEP 604) or builtin generics like `list[int]` (PEP 585) in annotations that
  are evaluated at runtime. Use `typing.List`, `typing.Optional`, `typing.Union`,
  etc. `from __future__ import annotations` is acceptable in new modules but the
  codebase currently uses explicit `typing` imports — match the surrounding file.
- **stdout is sacred.** `stdout` carries only the line-delimited JSON-RPC 2.0
  message stream that the MCP host reads. Never `print()` to stdout, never write
  to `sys.stdout` outside the bridge's framed writer. All diagnostics,
  warnings, and debug output go to **stderr** via
  `roblox_studio_mcp.core._log.get_logger`, whose level is controlled by
  `ROBLOX_STUDIO_MCP_LOG_LEVEL`.
- Keep modules single-purpose (see the module table in the README).
- Prefer clear names and short functions over cleverness. Add a docstring to new
  modules, classes, and non-obvious functions.

## Pull request process

1. Fork and branch from `main` (e.g. `fix/stderr-drainer-race`).
2. Make the change, add tests, run `python -m pytest` and `ruff check .` /
   `ruff format .`.
3. Update `README.md` if behavior or CLI surface changes.
4. Add an entry under `## [Unreleased]` in `CHANGELOG.md` (Added / Fixed /
   Changed).
5. Open the PR with a clear description of the problem and the fix. Link any
   related issue. Keep PRs focused — one logical change per PR.

## Commit style

- Imperative mood, concise subject line (≤ 72 chars): `Fix stderr drainer exit race`.
- Explain the *why* in the body when it is not obvious from the diff.
- One logical change per commit where practical.

## Reporting bugs

Open an issue with: OS and version, Python version, the host IDE, the output of
`python -m roblox_studio_mcp doctor`, and (if relevant) a stderr log captured
with `ROBLOX_STUDIO_MCP_LOG_LEVEL=DEBUG`. For security issues, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.
