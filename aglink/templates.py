"""Starter content written by `aglink init`."""

AGENTS_MD = """\
# Project — Agent Instructions

> Canonical instructions for every coding agent. Edit this file; run `aglink sync`.

## Overview

Describe what this project is and what you want agents to help with.

## Conventions

- Code style, naming, and structure rules go here.
- Commands agents should use (build, test, lint).

## Guardrails

- What agents must NOT do (e.g. never touch prod config, never force-push).
"""

GLOBAL_AGENTS_MD = """\
# Personal Agent Instructions

> Machine-wide rules for every project. AgLink prepends this to each project's
> own AGENTS.md, so keep it about *you*, not about any one codebase.

## About me

- Preferred languages, tools, and workflow.

## Style

- Conventions you want every agent to follow everywhere.
"""

GLOBAL_CONFIG_TOML = """\
# AgLink machine-wide configuration.
# Every project inherits these; a project's own config.toml overrides them.

[aglink]
targets = ["claude", "codex", "copilot", "opencode"]

[options]
banner = true
global_configs = true
"""

MCP_JSON = """\
{
  "mcpServers": {
    "aglink": {
      "command": "python",
      "args": ["-m", "aglink", "serve"],
      "env": {}
    }
  }
}
"""

CONFIG_TOML = """\
# AgLink configuration

[aglink]
# Which agents to project the canonical workspace into.
targets = ["claude", "codex", "copilot", "opencode"]

[mcp]
# When true, project only the AgLink server to agents and proxy every other
# canonical MCP server behind it.
gateway = false
gateway_name = "aglink"

[options]
# Prepend an "auto-generated" banner to projected files.
banner = true

# Also merge into config files outside the project (e.g. ~/.codex/config.toml).
# AgLink only rewrites its own clearly-marked block and backs the file up first.
global_configs = true
"""
