from __future__ import annotations

import json
import sys


TOOLS = [
    {
        "name": "echo",
        "description": "Echo back the provided text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
]


def read_message() -> dict | None:
    first = sys.stdin.buffer.readline()
    if not first:
        return None
    if not first.startswith(b"Content-Length:"):
        return json.loads(first.decode("utf-8"))
    length = int(first.split(b":", 1)[1].strip())
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(msg: dict) -> None:
    body = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(
        b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n"
    )
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-upstream", "version": "1.0"},
                },
            }
        )
    elif method == "tools/list":
        write_message(
            {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
        )
    elif method == "tools/call":
        params = msg.get("params", {})
        text = params.get("arguments", {}).get("text", "")
        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"upstream:{text}"}],
                    "isError": False,
                },
            }
        )
