"""AgLink MCP server — session handoff + shared memory over stdio.

Pure-stdlib implementation of the MCP stdio transport (newline-delimited
JSON-RPC 2.0). Implements `initialize`, `ping`, `tools/list`, `tools/call`.

Any MCP-capable agent (Claude Code, Codex, Copilot, OpenCode...) connects to
this same server, so a checkpoint written by one agent is instantly resumable
by another — that's the cross-agent continuity story.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__
from .core import find_root
from .store import MEMORY_TYPES, MemoryStore, SessionStore

PROTOCOL_VERSION = "2025-06-18"

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
                    "type": "array", "items": {"type": "string"},
                    "description": "Ordered concrete next actions.",
                },
                "files_touched": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Files read/edited and why (path — reason).",
                },
                "decisions": {
                    "type": "array", "items": {"type": "string"},
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
                },
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
                    "type": "string", "enum": list(MEMORY_TYPES),
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
        "description": "Keyword-search the shared cross-agent memory; returns the best-matching facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
            },
            "required": ["query"],
        },
    },
]


class Server:
    def __init__(self, root: Path):
        self.sessions = SessionStore(root)
        self.memory = MemoryStore(root)

    # -- tool implementations ------------------------------------------------
    def call(self, name: str, args: dict) -> str:
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
                f"Checkpoint saved: {record['id']}\n"
                f"Another agent can resume it with session_resume."
            )
        if name == "session_resume":
            record = self.sessions.get(args.get("session_id"))
            if record is None:
                wanted = args.get("session_id")
                return (
                    f"No checkpoint found with id {wanted!r}."
                    if wanted else "No checkpoints saved yet."
                )
            return SessionStore.brief(record)
        if name == "session_list":
            records = self.sessions.list()
            if not records:
                return "No checkpoints saved yet."
            return "\n".join(
                f"- {r['id']}  agent={r.get('agent') or '?'}  goal={r.get('goal') or r['summary'][:60]}"
                for r in records
            )
        if name == "memory_append":
            saved = self.memory.append(
                args["fact"], args.get("type", "project"), args.get("name", "")
            )
            return f"Memory saved: {saved['name']} (type={saved['type']})"
        if name == "memory_search":
            hits = self.memory.search(args["query"])
            if not hits:
                return "No matching memories."
            return "\n\n---\n\n".join(
                f"[{h['name']}] (score {h['score']})\n{h['content']}" for h in hits
            )
        raise ValueError(f"unknown tool: {name}")

    # -- JSON-RPC plumbing ----------------------------------------------------
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
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = msg.get("params", {})
                text = self.call(params.get("name", ""), params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            elif not is_request:
                return None  # notifications (initialized, cancelled...) need no reply
            else:
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
        except Exception as exc:  # tool errors -> in-band tool failure
            if method == "tools/call":
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"error: {exc}"}],
                        "isError": True,
                    },
                }
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": str(exc)},
            }

        return {"jsonrpc": "2.0", "id": msg_id, "result": result} if is_request else None


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
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
