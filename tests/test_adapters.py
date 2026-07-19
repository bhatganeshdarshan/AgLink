"""Tests for the OpenCode adapter and global-config merging.

Both write into files the user already owns, so the critical property under
test is: AgLink preserves everything it doesn't manage.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aglink import globalcfg  # noqa: E402
from aglink.adapters import render_opencode  # noqa: E402
from aglink.core import Canonical  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  -> {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def canonical_for(root):
    return Canonical(
        root=root,
        agents_md="# Rules\n",
        mcp_servers={"aglink": {"command": "python",
                                "args": ["-m", "aglink", "serve"], "env": {}}},
    )


tmp = Path(tempfile.mkdtemp())
try:
    # --- OpenCode: fresh project ------------------------------------------
    print("== OpenCode adapter ==")
    out = render_opencode(canonical_for(tmp))
    check("emits AGENTS.md", "AGENTS.md" in out)
    cfg = json.loads(out["opencode.json"])
    check("mcp.aglink uses single argv array",
          cfg["mcp"]["aglink"]["command"] == ["python", "-m", "aglink", "serve"],
          str(cfg["mcp"]["aglink"]))
    check("marks server enabled + local",
          cfg["mcp"]["aglink"]["enabled"] is True
          and cfg["mcp"]["aglink"]["type"] == "local")
    check("sets $schema", cfg.get("$schema", "").endswith("config.json"))

    # --- OpenCode: preserves the user's existing settings -----------------
    (tmp / "opencode.json").write_text(json.dumps({
        "theme": "tokyonight",
        "model": "anthropic/claude-opus-4-8",
        "mcp": {"my-own": {"type": "local", "command": ["foo"], "enabled": True}},
    }, indent=2), encoding="utf-8")
    cfg2 = json.loads(render_opencode(canonical_for(tmp))["opencode.json"])
    check("keeps unrelated user keys", cfg2.get("theme") == "tokyonight"
          and cfg2.get("model") == "anthropic/claude-opus-4-8", str(cfg2))
    check("keeps the user's own mcp server", "my-own" in cfg2["mcp"], str(cfg2["mcp"]))
    check("adds aglink alongside it", "aglink" in cfg2["mcp"])

    # --- OpenCode: refuses to touch an unparseable file -------------------
    (tmp / "opencode.json").write_text("{ this is not json", encoding="utf-8")
    check("skips unparseable opencode.json",
          "opencode.json" not in render_opencode(canonical_for(tmp)))

    # --- Global config merge ----------------------------------------------
    print("== Global config merge (~/.codex/config.toml style) ==")
    gpath = tmp / "codex-config.toml"
    original = (
        "# my own codex config\n"
        "model = \"gpt-5\"\n\n"
        "[mcp_servers.mine]\n"
        "command = \"node\"\n"
    )
    gpath.write_text(original, encoding="utf-8")

    action = globalcfg.merge_block(gpath, '[mcp_servers.aglink]\ncommand = "python"')
    text = gpath.read_text(encoding="utf-8")
    check("first merge appends", action == "appended", action)
    check("preserves user comment", "# my own codex config" in text)
    check("preserves user settings", 'model = "gpt-5"' in text)
    check("preserves user's own server", "[mcp_servers.mine]" in text)
    check("adds aglink block", "[mcp_servers.aglink]" in text)
    check("wrote a backup", (tmp / "codex-config.toml.aglink-backup").exists())

    check("re-merge is idempotent",
          globalcfg.merge_block(gpath, '[mcp_servers.aglink]\ncommand = "python"')
          == "unchanged")

    action = globalcfg.merge_block(gpath, '[mcp_servers.aglink]\ncommand = "py"')
    text2 = gpath.read_text(encoding="utf-8")
    check("changed body updates in place", action == "updated", action)
    check("update kept user content", "# my own codex config" in text2
          and "[mcp_servers.mine]" in text2)
    check("update replaced old value", 'command = "py"' in text2
          and text2.count("[mcp_servers.aglink]") == 1)

    check("dry run writes nothing",
          globalcfg.merge_block(gpath, "[mcp_servers.aglink]\ncommand = \"other\"",
                                dry_run=True) == "updated"
          and 'command = "py"' in gpath.read_text(encoding="utf-8"))

    fresh = tmp / "nested" / "new-config.toml"
    check("creates missing file",
          globalcfg.merge_block(fresh, "[x]\ny = 1") == "created" and fresh.exists())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ADAPTER + GLOBAL MERGE TESTS PASSED")
