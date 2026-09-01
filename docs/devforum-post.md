# DevForum post draft

**Where:** #community-resources (Community Resources). Discourse renders Markdown, so this file can be
pasted almost as-is. Swap the placeholder image links for real uploads before posting.

**Suggested title:**
> Fix Roblox Studio MCP: “expect initialized request”, `mcp.bat` errors, and the endless “Working…” hang

**Tags:** `mcp`, `ai`, `claude`, `cursor`, `studio`, `open-source`

---

## The problem

Roblox Studio ships a native **Model Context Protocol** server (Beta Features → Model Context
Protocol). It lets AI IDEs — Claude Desktop, Cursor, Claude Code, Antigravity, OpenCode, Windsurf —
drive Studio: insert models, run code, read the DataModel, etc.

Wired up the way Studio configures it, it tends to break in one of these ways:

**1. Handshake crash — the connection closes immediately**
```
Error: expect initialized request, but received: Some(Request(... method: "server/discover" ...))
: connection closed: calling "initialize": client is closing: EOF
```
Modern MCP hosts send a `server/discover` probe first. Studio’s server requires `initialize` first and
drops the connection.

**2. `mcp.bat` syntax errors on Windows**
```
'else' is not recognized as an internal or external command...
'"%B/..\StudioMCP.exe"' is not recognized as an internal or external command...
```
The generated `%LOCALAPPDATA%\Roblox\mcp.bat` puts `else` on its own line — invalid in `cmd.exe`.

**3. The agent hangs on “Working…” forever**
The server writes diagnostics to `stderr`. If nothing drains that pipe, Windows fills the OS buffer
and the process blocks permanently.

**4. It works, then stops after a Studio update**
Studio auto-updates ~weekly and rewrites its own launcher/config, re-injecting the broken entry.

**5. Tools silently fail after switching places or restarting Studio**
The server binds to a specific Studio instance; when that changes, calls just error out.

---

## The fix

**[Universal Roblox Studio MCP Bridge](https://github.com/Cpleasance/roblox-studio-mcp-bridge)** — a
small, dependency-free Python bridge that sits between your AI IDE and Studio’s own MCP server and
handles all five:

| Problem | What the bridge does |
|---|---|
| `server/discover` crash | Answers the probe itself by proxying `tools/list` — it never reaches the server out of order |
| stderr deadlock | Dedicated threads continuously drain `stdout` **and** `stderr` |
| Config wiped by updates | The IDE entry runs `roblox-studio-mcp`, which the updater never touches — and it auto-removes the re-injected `mcp.bat` entry on every startup |
| Wrong Studio build picked | Scans every install root, prefers the current Beta build, breaks ties by newest |
| Session disconnects | Auto-discovers the active Studio instance and transparently re-binds + retries |

It only launches Roblox’s own local `StudioMCP` executable and edits local IDE config files — no
network listeners, MIT licensed, 150+ tests + CI.

---

## Install

**1.** In Studio: File → Beta Features → **Model Context Protocol** → restart, open a place.

**2.** Install and wire up every IDE it finds:
```
uvx roblox-studio-mcp inject
```
(or `pip install roblox-studio-mcp && roblox-studio-mcp inject`, or grab the repo and double-click
`install.bat` / `install.command`)

**3.** Restart your AI IDE. Run `roblox-studio-mcp doctor` any time to check status.

---

## Links

- Repo + docs: https://github.com/Cpleasance/roblox-studio-mcp-bridge
- Issues / feature requests: https://github.com/Cpleasance/roblox-studio-mcp-bridge/issues

Unofficial community tool, not affiliated with Roblox. Feedback and PRs welcome — especially reports
from IDE/OS combos I can’t test.

---

<!-- Optional: embed a 15-30s GIF of an agent inserting a model / running code in Studio here. -->
