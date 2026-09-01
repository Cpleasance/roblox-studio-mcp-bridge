# Security Policy

## Supported versions

This project is released from a single line. Security fixes are applied to the
latest released version only.

| Version | Supported |
|---|---|
| 1.2.x   | Yes       |
| < 1.2   | No        |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub Security Advisories:

1. Go to the repository's **Security** tab →
   **Report a vulnerability** (GitHub Private Vulnerability Reporting), or open
   <https://github.com/Cpleasance/roblox-studio-mcp-bridge/security/advisories/new>.
2. Include: affected version, OS and Python version, a description of the issue,
   reproduction steps, and the impact you believe it has.

You can expect an initial acknowledgement within about 7 days. Once a fix is
ready we will coordinate a release and, with your permission, credit you in the
advisory and changelog.

## Scope

What this tool actually does, so you can calibrate reports:

- **Spawns a local child process:** Roblox Studio's own `StudioMCP` executable,
  discovered on the local machine (or the path you set via
  `ROBLOX_STUDIO_MCP_PATH` / `STUDIO_MCP_PATH`). It is treated as trusted local
  software.
- **Reads and writes local IDE config files** during `inject` / `eject`
  (`claude_desktop_config.json`, `.cursor/mcp.json`, `.opencode/mcp.json`,
  `.antigravity/mcp_config.json`). It backs up any file it modifies.
- **Communicates only over stdio pipes** between the host IDE, this bridge, and
  the `StudioMCP` child process.
- **Opens no network listeners** and makes no outbound network connections.

In scope: path/executable resolution that could run an unintended binary,
config-file handling that could corrupt or leak data, JSON-RPC handling flaws,
and privilege or injection issues in the CLI. Out of scope: vulnerabilities in
Roblox Studio or `StudioMCP` itself (report those to Roblox), and issues that
require an already-compromised local account.
