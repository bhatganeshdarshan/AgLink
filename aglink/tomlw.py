"""Minimal TOML writer — just enough to emit `[mcp_servers.*]` tables for Codex.

Python's stdlib can read TOML (`tomllib`) but not write it, and we don't want a
third-party dependency for the projector. This handles the small, known shape we
produce: string keys mapping to str / bool / int / list[str] / nested dict.
"""
from __future__ import annotations


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    raise TypeError(f"unsupported TOML scalar: {type(value)!r}")


def dumps_table(prefix: str, table: dict) -> str:
    """Serialize one dict as a TOML table headed `[prefix]`, recursing into
    nested dicts as sub-tables (`[prefix.child]`)."""
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    nested = {k: v for k, v in table.items() if isinstance(v, dict)}

    lines = [f"[{prefix}]"]
    for key, value in scalars.items():
        lines.append(f"{key} = {_fmt(value)}")
    out = "\n".join(lines)

    for key, sub in nested.items():
        out += "\n\n" + dumps_table(f"{prefix}.{key}", sub)
    return out
