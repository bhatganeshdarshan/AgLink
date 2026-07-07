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

MCP_JSON = """\
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "env": {}
    }
  }
}
"""

CONFIG_TOML = """\
# AgLink configuration

[aglink]
# Which agents to project the canonical workspace into.
targets = ["claude", "codex", "copilot"]

[options]
# Prepend an "auto-generated" banner to projected files.
banner = true
"""
