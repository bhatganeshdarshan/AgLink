"""AgLink MCP server: session handoff, shared memory, and optional MCP gateway."""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__
from .core import Canonical, find_root, load
from .store import MEMORY_TYPES, MemoryStore, SessionStore

PROTOCOL_VERSION = "2025-06-18"
TOOL_SEP = "__"

TOOLS = [
    {
        "name": "session_checkpoint",
        "description": (
            "Save a handoff checkpoint of the current work session so ANOTHER "
            "coding agent can resume it (e.g. when running low on context). "
            "Include everything the next agent needs to continue without "
            "re-reading the whole conversation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Where things stand: what was done, current state, open problems.",
                },
                "goal": {"type": "string", "description": "The overall task goal."},
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered concrete next actions.",
                },
                "files_touched": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files read/edited and why (path - reason).",
                },
                "decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Decisions already made that must not be re-litigated.",
                },
                "agent": {
                    "type": "string",
                    "description": "Name of the agent writing this checkpoint (e.g. 'claude-code').",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "session_resume",
        "description": (
            "Load a previously saved session checkpoint (latest by default) as a "
            "handoff brief. Call this FIRST when asked to continue work started "
            "in another coding agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Specific checkpoint id; omit for the most recent.",
                }
            },
        },
    },
    {
        "name": "session_list",
        "description": "List all saved session checkpoints (id, agent, goal).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_append",
        "description": (
            "Save a durable fact to the shared cross-agent memory (project "
            "conventions, user preferences, decisions worth keeping)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember."},
                "type": {
                    "type": "string",
                    "enum": list(MEMORY_TYPES),
                    "description": "Kind of memory (default: project).",
                },
                "name": {
                    "type": "string",
                    "description": "Optional short title used for the memory's slug.",
                },
            },
            "required": ["fact"],
        },
    },
    {
        "name": "memory_search",
        "description": "Keyword-search the shared memory; returns the best-matching facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."}
            },
            "required": ["query"],
        },
    },
]


def _tool_copy(tool: dict) -> dict:
    return json.loads(json.dumps(tool))


def _extract_text(result: dict) -> str:
    parts = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
    if parts:
        return "\n".join(part for part in parts if part)
    return json.dumps(result)


def _read_message(stream) -> dict:
    first = stream.readline()
    if not first:
        raise EOFError("upstream MCP server closed stdout")

    if first.startswith(b"Content-Length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            line = stream.readline()
            if not line:
                raise EOFError("upstream MCP server closed mid-header")
            if line in (b"\r\n", b"\n"):
                break
        body = stream.read(length)
        if len(body) != length:
            raise EOFError("upstream MCP server closed mid-frame")
        return json.loads(body.decode("utf-8"))

    return json.loads(first.decode("utf-8"))


def _write_message(stream, msg: dict) -> None:
    # MCP stdio transport is newline-delimited JSON (NOT LSP Content-Length
    # framing). This must match how real servers — and aglink's own serve() —
    # read their stdin, or the upstream deadlocks waiting for a newline.
    stream.write(json.dumps(msg).encode("utf-8") + b"\n")
    stream.flush()


class UpstreamClient:
    """Lazy stdio client for one upstream MCP server."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.proc: subprocess.Popen[bytes] | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        if self.proc is not None:
            return
        command = self.cfg.get("command")
        if not command:
            raise ValueError(f"server {self.name!r} has no command")

        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in self.cfg.get("env", {}).items()})
        self.proc = subprocess.Popen(
            [command, *self.cfg.get("args", [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            cwd=str(self.cfg.get("cwd") or Path.cwd()),
            env=env,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aglink", "version": __version__},
            },
        )
        self.notify("notifications/initialized", {})

    def request(self, method: str, params: dict | None = None) -> dict:
        self._ensure_started()
        assert self.proc is not None and self.proc.stdin and self.proc.stdout

        with self._lock:
            msg_id = next(self._ids)
            _write_message(
                self.proc.stdin,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "method": method,
                    "params": params or {},
                },
            )
            while True:
                reply = _read_message(self.proc.stdout)
                if "id" not in reply or reply.get("id") != msg_id:
                    continue
                if "error" in reply:
                    raise RuntimeError(reply["error"].get("message", "upstream error"))
                return reply.get("result", {})

    def notify(self, method: str, params: dict | None = None) -> None:
        self._ensure_started()
        assert self.proc is not None and self.proc.stdin
        with self._lock:
            _write_message(
                self.proc.stdin,
                {"jsonrpc": "2.0", "method": method, "params": params or {}},
            )

    def list_tools(self) -> list[dict]:
        return self.request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request(
            "tools/call", {"name": name, "arguments": arguments}
        )

    def close(self) -> None:
        if self.proc is None:
            return
        if self.proc.stdin:
            self.proc.stdin.close()
        if self.proc.stdout:
            self.proc.stdout.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        self.proc = None


class Gateway:
    def __init__(self, canonical: Canonical):
        self._clients = {
            name: UpstreamClient(name, cfg)
            for name, cfg in canonical.gateway_upstreams().items()
            if cfg.get("command")
        }

    def list_tools(self) -> list[dict]:
        tools = [_tool_copy(tool) for tool in TOOLS]
        for server_name, client in sorted(self._clients.items()):
            for tool in client.list_tools():
                proxied = _tool_copy(tool)
                original = proxied["name"]
                proxied["name"] = f"{server_name}{TOOL_SEP}{original}"
                prefix = f"Proxied from MCP server '{server_name}' as '{original}'. "
                proxied["description"] = prefix + proxied.get("description", "")
                tools.append(proxied)
        return tools

    def call(self, name: str, args: dict) -> tuple[bool, str]:
        server_name, bare_name = self._split_name(name)
        if server_name is None:
            return False, ""
        client = self._clients.get(server_name)
        if client is None:
            raise ValueError(f"unknown proxied MCP server: {server_name}")
        result = client.call_tool(bare_name, args)
        return bool(result.get("isError")), _extract_text(result)

    def _split_name(self, name: str) -> tuple[str | None, str]:
        server_name, sep, bare_name = name.partition(TOOL_SEP)
        if not sep or server_name not in self._clients:
            return None, name
        return server_name, bare_name

    def close(self) -> None:
        for client in self._clients.values():
            client.close()


class Server:
    def __init__(self, root: Path):
        self.sessions = SessionStore(root)
        self.memory = MemoryStore(root)
        self.gateway = Gateway(load(root))

    def list_tools(self) -> list[dict]:
        return self.gateway.list_tools()

    def call(self, name: str, args: dict) -> tuple[bool, str]:
        if name == "session_checkpoint":
            record = self.sessions.checkpoint(
                summary=args["summary"],
                goal=args.get("goal", ""),
                next_steps=args.get("next_steps"),
                files_touched=args.get("files_touched"),
                decisions=args.get("decisions"),
                agent=args.get("agent", ""),
            )
            return (
                False,
                f"Checkpoint saved: {record['id']}\n"
                f"Another agent can resume it with session_resume.",
            )
        if name == "session_resume":
            record = self.sessions.get(args.get("session_id"))
            if record is None:
                wanted = args.get("session_id")
                return (
                    True,
                    f"No checkpoint found with id {wanted!r}."
                    if wanted
                    else "No checkpoints saved yet.",
                )
            return False, SessionStore.brief(record)
        if name == "session_list":
            records = self.sessions.list()
            if not records:
                return False, "No checkpoints saved yet."
            return (
                False,
                "\n".join(
                    f"- {r['id']}  agent={r.get('agent') or '?'}  "
                    f"goal={r.get('goal') or r['summary'][:60]}"
                    for r in records
                ),
            )
        if name == "memory_append":
            saved = self.memory.append(
                args["fact"], args.get("type", "project"), args.get("name", "")
            )
            return False, f"Memory saved: {saved['name']} (type={saved['type']})"
        if name == "memory_search":
            hits = self.memory.search(args["query"])
            if not hits:
                return False, "No matching memories."
            return (
                False,
                "\n\n---\n\n".join(
                    f"[{h['name']}] (score {h['score']})\n{h['content']}" for h in hits
                ),
            )
        proxied, text = self.gateway.call(name, args)
        if text:
            return proxied, text
        raise ValueError(f"unknown tool: {name}")

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        msg_id = msg.get("id")
        is_request = "id" in msg

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": msg.get("params", {}).get(
                        "protocolVersion", PROTOCOL_VERSION
                    ),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aglink", "version": __version__},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                params = msg.get("params", {})
                is_error, text = self.call(
                    params.get("name", ""), params.get("arguments", {})
                )
                result = {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_error,
                }
            elif not is_request:
                return None
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
        except Exception as exc:
            if method == "tools/call":
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"error: {exc}"}],
                        "isError": True,
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(exc)},
            }

        return {"jsonrpc": "2.0", "id": msg_id, "result": result} if is_request else None

    def close(self) -> None:
        self.gateway.close()


def serve(root: Path | None = None) -> int:
    server = Server(root or find_root())
    stdin = sys.stdin
    stdout = sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply: dict | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
