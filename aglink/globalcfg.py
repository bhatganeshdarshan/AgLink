"""Surgical, marker-delimited merging into config files AgLink doesn't own.

Files like `~/.codex/config.toml` hold the user's own servers, settings and
comments. We must never rewrite them wholesale (a TOML round-trip would drop
every comment). Instead we own exactly one clearly-marked region and rewrite
only that, leaving every other byte untouched.
"""
from __future__ import annotations

from pathlib import Path

BEGIN = "# >>> AGLINK MANAGED - do not edit inside this block"
END = "# <<< AGLINK MANAGED"


def render_block(body: str) -> str:
    return f"{BEGIN}\n{body.strip()}\n{END}\n"


def merge_block(path: Path, body: str, dry_run: bool = False) -> str:
    """Insert or update AgLink's marked block in `path`.

    Returns one of: "unchanged", "created", "updated", "appended".
    A one-time `.aglink-backup` is written before the first modification of an
    existing file, so a bad merge is always recoverable.
    """
    block = render_block(body)

    if not path.exists():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(block, encoding="utf-8")
        return "created"

    original = path.read_text(encoding="utf-8")
    start = original.find(BEGIN)

    if start == -1:
        if block.strip() in original:
            return "unchanged"
        separator = "" if original.endswith("\n") else "\n"
        merged = original + separator + "\n" + block
        action = "appended"
    else:
        end = original.find(END, start)
        if end == -1:  # truncated/corrupted block: replace to end of file
            end_of_block = len(original)
        else:
            end_of_block = end + len(END)
            if original[end_of_block:end_of_block + 1] == "\n":
                end_of_block += 1
        merged = original[:start] + block + original[end_of_block:]
        action = "updated"

    if merged == original:
        return "unchanged"

    if not dry_run:
        backup = path.with_suffix(path.suffix + ".aglink-backup")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(merged, encoding="utf-8")
    return action
