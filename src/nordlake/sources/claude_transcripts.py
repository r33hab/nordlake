"""Usage metadata from Claude Code session transcripts.

Transcripts live in `~/.claude/projects/<project>/<session>.jsonl`.

What is kept per line:
- assistant turns: message id, model, token usage (input, cache write, cache read, output),
  stop reason, timestamp, session, project, git branch, Claude Code version, content block kinds
- user turns: uuid, timestamp, session, project, and whether the turn was a tool result

What is never kept: prompt text, model output, tool inputs or results, file contents. The
transcripts hold everything typed and everything Claude wrote back; this source reads them
for cost and activity only, so the bronze layer stays safe to keep around.

One API message is written to the transcript as several lines, one per content block, and
each line repeats the same `usage`. The record key is the message id, so the silver layer
collapses them; counting lines instead would overstate cost by roughly 2 to 3 times.

Cursor: JSON `{"files": {"<path>": <byte offset>}}`. Transcripts are append-only, so each
run reads only the bytes after the stored offset and stops before an incomplete last line.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nordlake.sources.base import Batch, Record

log = logging.getLogger(__name__)


@dataclass
class ClaudeTranscriptsSource:
    projects_dir: Path = field(default_factory=lambda: Path.home() / ".claude" / "projects")
    hash_projects: bool = False
    batch_size: int = 5000
    name: str = "claude_transcripts"

    def fetch(self, cursor: str | None) -> Iterator[Batch]:
        offsets: dict[str, int] = json.loads(cursor).get("files", {}) if cursor else {}
        records: list[Record] = []
        files = sorted(Path(self.projects_dir).expanduser().glob("*/*.jsonl"))
        log.info("claude_transcripts: scanning %d transcript files", len(files))

        for file in files:
            key = str(file)
            start = offsets.get(key, 0)
            size = file.stat().st_size
            if size < start:  # file was rewritten or truncated: start over
                start = 0
            if size == start:
                continue

            with file.open("rb") as handle:
                handle.seek(start)
                data = handle.read()
            end = data.rfind(b"\n")
            if end == -1:  # only a partial line so far
                continue

            project_hint = file.parent.name
            for line in data[:end].split(b"\n"):
                record = self._to_record(line, project_hint)
                if record is not None:
                    records.append(record)
            offsets[key] = start + end + 1

            if len(records) >= self.batch_size:
                yield Batch(records=records, cursor=json.dumps({"files": offsets}))
                records = []

        yield Batch(records=records, cursor=json.dumps({"files": offsets}))

    def _to_record(self, line: bytes, project_hint: str) -> Record | None:
        if not line.strip():
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None

        kind = obj.get("type")
        if kind not in ("assistant", "user"):
            return None
        timestamp = obj.get("timestamp")
        if not timestamp:
            return None
        when = _parse_dt(timestamp)

        base: dict[str, Any] = {
            "kind": kind,
            "ts": timestamp,
            "session_id": obj.get("sessionId"),
            "project": self._project_name(obj.get("cwd"), project_hint),
            "is_sidechain": bool(obj.get("isSidechain")),
            "git_branch": obj.get("gitBranch"),
            "cc_version": obj.get("version"),
        }
        message = obj.get("message") or {}
        content = message.get("content")

        if kind == "assistant":
            message_id = message.get("id")
            if not message_id:
                return None
            usage = message.get("usage") or {}
            cache = usage.get("cache_creation") or {}
            blocks = (
                Counter(block.get("type") for block in content if isinstance(block, dict))
                if isinstance(content, list)
                else Counter()
            )
            payload = {
                **base,
                "message_id": message_id,
                "request_id": obj.get("requestId"),
                "model": message.get("model"),
                "stop_reason": message.get("stop_reason"),
                "input_tokens": usage.get("input_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_write_5m_tokens": cache.get("ephemeral_5m_input_tokens"),
                "cache_write_1h_tokens": cache.get("ephemeral_1h_input_tokens"),
                "blocks": dict(blocks),
            }
            return Record(key=f"assistant:{message_id}", updated_at=when, payload=payload)

        uuid = obj.get("uuid")
        if not uuid:
            return None
        is_tool_result = isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        )
        payload = {
            **base,
            "uuid": uuid,
            "is_tool_result": is_tool_result,
            "is_meta": bool(obj.get("isMeta")),
        }
        return Record(key=f"user:{uuid}", updated_at=when, payload=payload)

    def _project_name(self, cwd: str | None, hint: str) -> str:
        name = Path(cwd).name if cwd else hint
        if self.hash_projects:
            return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
        return name


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
