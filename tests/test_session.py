"""End-to-end test of the AgLink MCP server over real stdio.

Simulates the exact handoff story: "agent A" (claude-code) checkpoints,
then "agent B" (codex) — a SEPARATE server process — resumes and searches
memory. Uses a throwaway project dir so the real repo isn't polluted.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PROJ = HERE / "fake-project"
AGLINK_SRC = str(HERE.parent)

failures = []


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -> {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


class Client:
    """Minimal MCP client speaking newline-delimited JSON-RPC to a subprocess."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "aglink", "serve"],
            cwd=PROJ,
            env={"PYTHONPATH": AGLINK_SRC, "SYSTEMROOT": "C:\\Windows"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
        self._id = 0

    def request(self, method, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def tool(self, name, args):
        resp = self.request("tools/call", {"name": name, "arguments": args})
        return resp["result"]["content"][0]["text"], resp["result"].get("isError")

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


# fresh throwaway project
if PROJ.exists():
    shutil.rmtree(PROJ)
(PROJ / ".agentsync").mkdir(parents=True)

print("== Agent A (claude-code): handshake, checkpoint, memory ==")
a = Client()
init = a.request("initialize", {"protocolVersion": "2025-06-18",
                                "capabilities": {}, "clientInfo": {"name": "test"}})
check("initialize returns serverInfo aglink",
      init["result"]["serverInfo"]["name"] == "aglink", json.dumps(init))
a.notify("notifications/initialized")

tools = a.request("tools/list")["result"]["tools"]
names = {t["name"] for t in tools}
check("tools/list exposes all 5 tools",
      names == {"session_checkpoint", "session_resume", "session_list",
                "memory_append", "memory_search"}, str(names))

text, err = a.tool("session_checkpoint", {
    "summary": "Built the parser module; 2 failing tests remain in test_edge.py.",
    "goal": "Add CSV import feature",
    "next_steps": ["Fix test_empty_row", "Fix test_bom_header", "Run full suite"],
    "files_touched": ["src/parser.py — new module", "tests/test_edge.py — added cases"],
    "decisions": ["Use stdlib csv module, not pandas"],
    "agent": "claude-code",
})
check("checkpoint saved", "Checkpoint saved" in text and not err, text)

text, err = a.tool("memory_append", {
    "fact": "User prefers stdlib-only solutions; avoid adding dependencies.",
    "type": "user", "name": "stdlib preference",
})
check("memory saved", "Memory saved" in text and not err, text)
a.close()

print("== Agent B (codex): separate process resumes the session ==")
b = Client()
b.request("initialize", {"protocolVersion": "2025-06-18",
                         "capabilities": {}, "clientInfo": {"name": "codex"}})
b.notify("notifications/initialized")

brief, err = b.tool("session_resume", {})
check("resume returns handoff brief", "Session handoff" in brief and not err)
check("brief has goal", "Add CSV import feature" in brief)
check("brief has decisions", "stdlib csv module" in brief)
check("brief has ordered next steps", "1. Fix test_empty_row" in brief)

hits, err = b.tool("memory_search", {"query": "dependencies stdlib"})
check("memory search finds fact from agent A", "stdlib-only" in hits and not err, hits)

text, _ = b.tool("session_list", {})
check("session_list shows the checkpoint", "agent=claude-code" in text, text)

# error paths
text, err = b.tool("session_resume", {"session_id": "nope"})
check("missing id handled gracefully", "No checkpoint found" in text)
resp = b.request("bogus/method")
check("unknown method -> -32601", resp.get("error", {}).get("code") == -32601)
b.close()

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
