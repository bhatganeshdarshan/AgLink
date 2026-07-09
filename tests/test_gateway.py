from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from aglink.adapters import render_claude
from aglink.core import load
from aglink.mcpserver import Server


class GatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        sync = self.root / ".agentsync"
        sync.mkdir()
        (sync / "AGENTS.md").write_text("# Test\n", encoding="utf-8")
        (sync / "config.toml").write_text(
            '[mcp]\ngateway = true\ngateway_name = "aglink"\n',
            encoding="utf-8",
        )
        upstream = (Path(__file__).parent / "fake_upstream.py").resolve()
        (sync / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "aglink": {
                            "command": "python",
                            "args": ["-m", "aglink", "serve"],
                        },
                        "echo": {
                            "command": sys.executable,
                            "args": [str(upstream)],
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_gateway_projection_emits_only_aglink(self) -> None:
        canonical = load(self.root)
        rendered = json.loads(render_claude(canonical)[".mcp.json"])
        self.assertEqual(list(rendered["mcpServers"]), ["aglink"])

    def test_gateway_lists_and_calls_upstream_tools(self) -> None:
        server = Server(self.root)
        try:
            listed = server.handle(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            )
            self.assertIsNotNone(listed)
            tools = listed["result"]["tools"]
            self.assertIn("session_checkpoint", [tool["name"] for tool in tools])
            self.assertIn("echo__echo", [tool["name"] for tool in tools])

            called = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "echo__echo",
                        "arguments": {"text": "hello"},
                    },
                }
            )
            self.assertIsNotNone(called)
            self.assertFalse(called["result"]["isError"])
            self.assertEqual(
                called["result"]["content"][0]["text"],
                "upstream:hello",
            )
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
