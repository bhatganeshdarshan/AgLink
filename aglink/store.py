"""Persistent stores for cross-agent session handoff and shared memory.

Everything lives under `.agentsync/` so it travels with the repo:

    .agentsync/
      sessions/<id>.json     one checkpoint per handoff
      memory/<slug>.md       one fact per file (frontmatter + body)
      memory/MEMORY.md       human-readable index of all memories
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .core import AGENTSYNC_DIR

MEMORY_TYPES = ("user", "feedback", "project", "reference")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
    return "-".join(words) or "note"


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
class SessionStore:
    def __init__(self, root: Path):
        self.dir = root / AGENTSYNC_DIR / "sessions"

    def checkpoint(
        self,
        summary: str,
        goal: str = "",
        next_steps: list[str] | None = None,
        files_touched: list[str] | None = None,
        decisions: list[str] | None = None,
        agent: str = "",
    ) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        record = {
            "id": session_id,
            "created": _now(),
            "agent": agent,
            "goal": goal,
            "summary": summary,
            "next_steps": next_steps or [],
            "files_touched": files_touched or [],
            "decisions": decisions or [],
        }
        path = self.dir / f"{session_id}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        records = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return records

    def get(self, session_id: str | None = None) -> dict | None:
        records = self.list()
        if not records:
            return None
        if session_id is None:
            return records[-1]  # ids are timestamps, so sorted order = age
        return next((r for r in records if r["id"] == session_id), None)

    @staticmethod
    def brief(record: dict) -> str:
        """Format a checkpoint as a handoff brief the resuming agent ingests."""
        lines = [
            f"# Session handoff — {record['id']}",
            f"- created: {record['created']}",
        ]
        if record.get("agent"):
            lines.append(f"- previous agent: {record['agent']}")
        if record.get("goal"):
            lines += ["", "## Goal", record["goal"]]
        lines += ["", "## Where things stand", record["summary"]]
        if record.get("decisions"):
            lines += ["", "## Decisions already made (do not re-litigate)"]
            lines += [f"- {d}" for d in record["decisions"]]
        if record.get("files_touched"):
            lines += ["", "## Files touched"]
            lines += [f"- {f}" for f in record["files_touched"]]
        if record.get("next_steps"):
            lines += ["", "## Next steps"]
            lines += [f"{i}. {s}" for i, s in enumerate(record["next_steps"], 1)]
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------
class MemoryStore:
    """Memory spanning two scopes.

    `project` memory lives in the repo and travels with it; `global` memory
    lives in ~/.agentsync/memory and follows you across every project. Search
    covers both so a personal preference is visible from any repo.
    """

    def __init__(self, root: Path, global_dir: Path | None = None):
        self.dir = root / AGENTSYNC_DIR / "memory"
        self.global_dir = (global_dir / "memory") if global_dir else None

    def _dir_for(self, scope: str) -> Path:
        if scope == "global" and self.global_dir is not None:
            return self.global_dir
        return self.dir

    def append(
        self,
        fact: str,
        mem_type: str = "project",
        name: str = "",
        scope: str = "project",
    ) -> dict:
        if mem_type not in MEMORY_TYPES:
            mem_type = "project"
        target_dir = self._dir_for(scope)
        scope = "global" if target_dir is self.global_dir else "project"
        target_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(name or fact)
        path = target_dir / f"{slug}.md"
        # Never silently merge distinct facts: suffix on collision.
        n = 2
        while path.exists():
            path = target_dir / f"{slug}-{n}.md"
            n += 1

        description = fact.strip().splitlines()[0][:100]
        body = (
            f"---\n"
            f"name: {path.stem}\n"
            f"description: {description}\n"
            f"metadata:\n"
            f"  type: {mem_type}\n"
            f"  created: {_now()}\n"
            f"---\n\n"
            f"{fact.strip()}\n"
        )
        path.write_text(body, encoding="utf-8")
        self._index_add(path.stem, description, target_dir)
        return {
            "name": path.stem, "file": path.name, "type": mem_type, "scope": scope
        }

    def _index_add(self, name: str, description: str, target_dir: Path) -> None:
        index = target_dir / "MEMORY.md"
        line = f"- [{name}]({name}.md) — {description}\n"
        if index.exists():
            index.write_text(
                index.read_text(encoding="utf-8") + line, encoding="utf-8"
            )
        else:
            index.write_text("# Shared agent memory\n\n" + line, encoding="utf-8")

    def entries(self) -> list[tuple[str, str, str]]:
        """All memory files across both scopes as (name, full_text, scope)."""
        found: list[tuple[str, str, str]] = []
        for scope, directory in (("global", self.global_dir), ("project", self.dir)):
            if directory is None or not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.name == "MEMORY.md":
                    continue
                found.append((path.stem, path.read_text(encoding="utf-8"), scope))
        return found

    def search(self, query: str, limit: int = 5) -> list[dict]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        scored = []
        for name, text, scope in self.entries():
            lower = text.lower()
            score = sum(lower.count(t) for t in terms)
            score += sum(3 for t in terms if t in name)  # name hits weigh more
            if score > 0:
                scored.append((score, name, text, scope))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [
            {"name": name, "score": score, "content": text, "scope": scope}
            for score, name, text, scope in scored[:limit]
        ]
