"""Per-source cursor persistence: one small JSON file per source, written atomically."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, source: str) -> Path:
        return self.root / f"{source}.json"

    def get(self, source: str) -> str | None:
        path = self._path(source)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("cursor")

    def set(self, source: str, cursor: str | None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(source)
        tmp = path.with_suffix(".json.tmp")
        body = {"cursor": cursor, "updated_at": datetime.now(UTC).isoformat()}
        tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def describe(self, source: str) -> dict:
        path = self._path(source)
        if not path.exists():
            return {"cursor": None, "updated_at": None}
        return json.loads(path.read_text(encoding="utf-8"))
