# AgLink

![alt text](image.png)

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
| Codex | `AGENTS.md` | `~/.codex/config.toml` |
| OpenCode | `AGENTS.md` | `opencode.json` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.vscode/mcp.json` |

Keeping these in sync by hand is error-prone. AgLink makes one source canonical
and generates the rest — every file above, including the ones outside your
project. No manual copy-pasting of config snippets.

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
aglink init --global  # scaffold the machine-wide layer in ~/.agentsync
aglink sync      # project canonical files into every enabled agent
aglink sync --check   # dry run — show what would change, write nothing
aglink sync --no-global  # skip files outside the project (~/.codex/config.toml)
aglink status    # show which projected files are in-sync / drifted / missing
aglink doctor    # detect installed agents and verify each one is wired up
aglink serve     # run the AgLink MCP server (session handoff + memory)
aglink sessions  # list saved session checkpoints
```

## Two layers: global + project

AgLink resolves a machine-wide layer under every project:

```
~/.agentsync/            your personal rules + always-on MCP servers
<repo>/.agentsync/       this repo's rules + servers
```

Run `aglink init --global` once, put your personal conventions in
`~/.agentsync/AGENTS.md`, and every project inherits them. Merge rules:

| Piece | Rule |
|---|---|
| `AGENTS.md` | **Concatenated** — global first, project second (specific reads last) |
| `mcp.json` | **Merged by name** — project entry wins on a collision |
| `config.toml` | **Key override** — project value wins, otherwise inherits global |
| `memory/` | **Both searchable** — `scope: "global"` for facts that follow you everywhere |

Opt a repo out with `use_global = false` under `[options]`. Point the layer
somewhere else with the `AGLINK_HOME` environment variable.

> When a global layer is active, `CLAUDE.md` holds the merged text instead of
> an `@import` (an import can't express a two-layer merge), so re-run
> `aglink sync` after editing instructions.

### Files AgLink doesn't own

Two targets write into files that hold your own settings, so AgLink **merges**
instead of overwriting:

- **`~/.codex/config.toml`** — AgLink rewrites only its own
  `# >>> AGLINK MANAGED` block, leaving your model settings, other MCP servers,
  comments and project trust levels byte-identical. A one-time
  `.aglink-backup` is written before the first change. Disable with
  `global_configs = false` or `--no-global`.
- **`opencode.json`** — AgLink merges its server into the `mcp` key and
  preserves every other key (theme, model, your own servers). If the file isn't
  valid JSON, AgLink leaves it completely alone.

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
- [x] **`doctor`** — detect installed agents and config drift automatically.
- [x] **OpenCode adapter** + automatic `~/.codex/config.toml` merging.
- [x] **Global layer** — machine-wide canonical workspace merged with per-repo.
- [ ] File watcher for auto-sync on `.agentsync/` edits.
- [ ] Cursor / Gemini / Windsurf adapters.
