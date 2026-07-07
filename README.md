# AgLink

**One canonical agent workspace, projected into every coding agent.**

You write your instructions, MCP servers, and (soon) memory once. AgLink
projects that single source of truth into the native config files each agent
expects — Claude Code, Codex/OpenCode, GitHub Copilot, and more — so they all
share the same brain.

## Why

Every coding agent invented its own conventions:

| Agent | Instructions | MCP config |
|---|---|---|
| Claude Code | `CLAUDE.md` | `.mcp.json` |
| Codex / OpenCode / Zed | `AGENTS.md` | `~/.codex/config.toml` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.vscode/mcp.json` |

Keeping these in sync by hand is error-prone. AgLink makes one source canonical
and generates the rest.

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
aglink init      # scaffold .agentsync/ (AGENTS.md, mcp.json, config.toml)
aglink sync      # project canonical files into every enabled agent
aglink sync --check   # dry run — show what would change, write nothing
aglink status    # show which projected files are in-sync / drifted / missing
aglink serve     # run the AgLink MCP server (session handoff + memory)
aglink sessions  # list saved session checkpoints
```

## Session handoff — continue in another agent

Every agent connects to the same AgLink MCP server (it's in the projected MCP
configs by default), which exposes:

| Tool | Purpose |
|---|---|
| `session_checkpoint` | Save a handoff brief: summary, goal, next steps, files touched, decisions |
| `session_resume` | Load the latest (or a specific) checkpoint and continue |
| `session_list` | List all checkpoints |
| `memory_append` | Save a durable fact to shared cross-agent memory |
| `memory_search` | Keyword-search the shared memory |

**The flow:** running low on tokens in Claude Code? Ask it to
"checkpoint this session". Open Codex (or any other agent), say
"resume the last aglink session" — it calls `session_resume` and picks up with
the goal, the decisions already made, the files touched, and the next steps.
State lives in `.agentsync/sessions/` and `.agentsync/memory/`, so it's
git-trackable and travels with the repo.

### Canonical workspace (`.agentsync/`)

- **`AGENTS.md`** — your instructions (the convergent cross-agent standard).
- **`mcp.json`** — MCP servers in the standard `{"mcpServers": {...}}` schema.
- **`config.toml`** — which agents to target, and options like the banner.

### What gets generated

- `CLAUDE.md` — a thin `@import` of the canonical `AGENTS.md` (true live single
  source; editing the canonical needs no re-sync for Claude).
- `.mcp.json` — 1:1 copy of your MCP config.
- `AGENTS.md` (repo root) — copy read by Codex, OpenCode, Zed, Cursor.
- `.agentsync/generated/codex.config.toml` — TOML snippet to merge into
  `~/.codex/config.toml` (Codex configures MCP globally).
- `.github/copilot-instructions.md` — Copilot instructions.
- `.vscode/mcp.json` — Copilot/VS Code MCP config (transformed schema).

AgLink **never overwrites a pre-existing file it didn't generate** — if you
already had a hand-written `CLAUDE.md`, it's skipped with a warning.

## Roadmap

- [x] **Config projector** — canonical → native files.
- [x] **Session handoff MCP server** — `checkpoint` / `resume` + shared memory
  as MCP tools, so you can run out of tokens in one agent and continue in
  another with full context.
- [ ] **MCP gateway** — one endpoint aggregating all your MCP servers, so every
  agent shares a single connection and config.
- [ ] **Global layer** — machine-wide canonical workspace merged with per-repo.
- [ ] **`doctor`** — detect installed agents and config drift automatically.
- [ ] Cursor / Gemini / Windsurf adapters.
