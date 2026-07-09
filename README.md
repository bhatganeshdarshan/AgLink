# AgLink

![LOGO](./image.png)

**One canonical agent workspace, projected into every coding agent.**

You write your instructions, MCP servers, and shared continuity once. AgLink
projects that source of truth into the native config files each agent expects
so Claude Code, Codex/OpenCode, GitHub Copilot, and future adapters can share
the same workspace brain.

## Why

Every coding agent invented its own conventions:

| Agent | Instructions | MCP config |
|---|---|---|
| Claude Code | `CLAUDE.md` | `.mcp.json` |
| Codex / OpenCode / Zed | `AGENTS.md` | `~/.codex/config.toml` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.vscode/mcp.json` |

Keeping these in sync by hand is error-prone. AgLink makes one source
canonical and generates the rest.

## Install

Requires Python 3.11+. No third-party dependencies.

```bash
# Run without installing:
python -m aglink --help

# Or install the `aglink` command:
pip install -e .
```

## Usage

```bash
aglink init           # scaffold .agentsync/ (AGENTS.md, mcp.json, config.toml)
aglink sync           # project canonical files into every enabled agent
aglink sync --check   # dry run; show what would change, write nothing
aglink status         # show which projected files are in-sync / drifted / missing
aglink serve          # run the AgLink MCP server (handoff + memory + gateway)
aglink sessions       # list saved session checkpoints
```

## Session handoff

Every agent connects to the same AgLink MCP server, which exposes:

| Tool | Purpose |
|---|---|
| `session_checkpoint` | Save a handoff brief: summary, goal, next steps, files touched, decisions |
| `session_resume` | Load the latest (or a specific) checkpoint and continue |
| `session_list` | List all checkpoints |
| `memory_append` | Save a durable fact to shared cross-agent memory |
| `memory_search` | Keyword-search the shared memory |

Running low on context in one agent? Ask it to checkpoint the session. Open
another agent and say "resume the last aglink session" and it can continue with
the saved goal, decisions, touched files, and next steps. State lives in
`.agentsync/sessions/` and `.agentsync/memory/`, so it travels with the repo.

## MCP gateway

AgLink can also act as an MCP gateway. Keep your real upstream servers in
`.agentsync/mcp.json`, then enable this in `.agentsync/config.toml`:

```toml
[mcp]
gateway = true
gateway_name = "aglink"
```

When gateway mode is on, `aglink sync` projects only the `aglink` server into
agent configs. AgLink then connects to every other canonical MCP server itself
and republishes their tools with namespaced names such as
`filesystem__read_file` or `github__search_repositories`.

## Canonical workspace

The canonical source lives in `.agentsync/`:

- `AGENTS.md` - cross-agent instructions.
- `mcp.json` - MCP servers in the standard `{"mcpServers": {...}}` schema.
- `config.toml` - target agents and options like banners and gateway mode.

## Generated outputs

- `CLAUDE.md` - a thin `@import` of the canonical `AGENTS.md`.
- `.mcp.json` - Claude Code MCP config.
- `AGENTS.md` at repo root - instruction copy for Codex/OpenCode/Zed/Cursor.
- `.agentsync/generated/codex.config.toml` - TOML snippet to merge into `~/.codex/config.toml`.
- `.github/copilot-instructions.md` - Copilot instructions.
- `.vscode/mcp.json` - Copilot / VS Code MCP config.

If gateway mode is enabled, those generated MCP configs contain only the AgLink
server entry; the upstream servers remain canonical inside `.agentsync/mcp.json`.

AgLink never overwrites a pre-existing file it did not generate. If you already
had a hand-written `CLAUDE.md`, it is skipped with a warning.

## Roadmap

- [x] Config projector - canonical to native agent files.
- [x] Session handoff MCP server - checkpoint/resume plus shared memory.
- [x] MCP gateway - one endpoint aggregating all canonical MCP servers.
- [ ] Global layer - machine-wide canonical workspace merged with per-repo.
- [ ] `doctor` - detect installed agents and config drift automatically.
- [ ] Cursor / Gemini / Windsurf adapters.
