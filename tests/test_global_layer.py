"""Tests for the machine-wide global layer merged under each project.

Precedence contract: instructions concatenate (global first), while MCP
servers and config keys are overridden by the project.
Uses AGLINK_HOME to point the "global" layer at a temp dir.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  -> {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


tmp = Path(tempfile.mkdtemp())
gdir = tmp / "global-agentsync"
proj = tmp / "proj"
(gdir).mkdir()
(proj / ".agentsync").mkdir(parents=True)
os.environ["AGLINK_HOME"] = str(gdir)

# Reload core so it picks up AGLINK_HOME cleanly.
from aglink import core  # noqa: E402
from aglink.adapters import render_claude  # noqa: E402
from aglink.store import MemoryStore  # noqa: E402

try:
    # global layer
    (gdir / "AGENTS.md").write_text("GLOBAL RULE: prefer stdlib.\n", encoding="utf-8")
    (gdir / "mcp.json").write_text(json.dumps({"mcpServers": {
        "aglink": {"command": "python", "args": ["-m", "aglink", "serve"]},
        "shared": {"command": "global-cmd"},
    }}), encoding="utf-8")
    (gdir / "config.toml").write_text(
        '[aglink]\ntargets = ["claude", "codex"]\n[options]\nbanner = true\n',
        encoding="utf-8",
    )
    # project layer
    (proj / ".agentsync" / "AGENTS.md").write_text(
        "PROJECT RULE: use pytest.\n", encoding="utf-8")
    (proj / ".agentsync" / "mcp.json").write_text(json.dumps({"mcpServers": {
        "shared": {"command": "project-cmd"},   # overrides global
        "only-here": {"command": "local-cmd"},
    }}), encoding="utf-8")
    (proj / ".agentsync" / "config.toml").write_text(
        '[aglink]\ntargets = ["claude"]\n', encoding="utf-8")

    print("== merge ==")
    c = core.load(proj)
    check("global layer detected", c.has_global, str(c.global_layer))
    check("global instructions included", "GLOBAL RULE" in c.agents_md)
    check("project instructions included", "PROJECT RULE" in c.agents_md)
    check("global text comes first",
          c.agents_md.index("GLOBAL RULE") < c.agents_md.index("PROJECT RULE"))
    check("layer headers present",
          core.GLOBAL_HEADER in c.agents_md and core.PROJECT_HEADER in c.agents_md)

    check("global-only server inherited", "aglink" in c.mcp_servers)
    check("project-only server present", "only-here" in c.mcp_servers)
    check("project overrides same-named server",
          c.mcp_servers["shared"]["command"] == "project-cmd",
          str(c.mcp_servers["shared"]))
    check("project config overrides global targets",
          c.targets == ["claude"], str(c.targets))
    check("unset project key inherits global", c.banner is True)

    print("== claude adapter switches off @import when global is active ==")
    out = render_claude(c)
    check("CLAUDE.md inlines merged text",
          "GLOBAL RULE" in out["CLAUDE.md"] and "PROJECT RULE" in out["CLAUDE.md"])
    check("no stale @import", "@.agentsync/AGENTS.md" not in out["CLAUDE.md"])

    print("== opt out ==")
    (proj / ".agentsync" / "config.toml").write_text(
        '[options]\nuse_global = false\n', encoding="utf-8")
    c2 = core.load(proj)
    check("use_global=false ignores global layer", not c2.has_global)
    check("instructions are project-only", "GLOBAL RULE" not in c2.agents_md)
    check("servers are project-only", "aglink" not in c2.mcp_servers)
    check("@import restored without global layer",
          "@.agentsync/AGENTS.md" in render_claude(c2)["CLAUDE.md"])

    print("== global memory ==")
    mem = MemoryStore(proj, gdir)
    mem.append("I always prefer tabs.", "user", "tabs", scope="global")
    mem.append("This repo uses 4 spaces.", "project", "spaces", scope="project")
    check("global memory written to global dir",
          (gdir / "memory" / "tabs.md").exists())
    check("project memory written to project dir",
          (proj / ".agentsync" / "memory" / "spaces.md").exists())
    hits = {h["name"]: h["scope"] for h in mem.search("prefer tabs spaces")}
    check("search spans both scopes",
          hits.get("tabs") == "global" and hits.get("spaces") == "project", str(hits))
finally:
    os.environ.pop("AGLINK_HOME", None)
    shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("GLOBAL LAYER TESTS PASSED")
