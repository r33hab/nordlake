"""The runner: pull batches from a source, land them in bronze, then advance the cursor."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from nordlake.sources.base import Source
from nordlake.state import StateStore
from nordlake.storage import BronzeWriter

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    source: str
    records: int
    files: int
    seconds: float
    cursor_before: str | None
    cursor_after: str | None


def run_source(source: Source, state: StateStore, writer: BronzeWriter) -> RunSummary:
    started = time.monotonic()
    cursor_before = state.get(source.name)
    cursor_after = cursor_before
    records = files = 0

    log.info("%s: starting from cursor %s", source.name, _short(cursor_before))
    for batch in source.fetch(cursor_before):
        path = writer.write(source.name, batch.records)
        if path is not None:
            files += 1
            records += len(batch.records)
            log.info("%s: wrote %d records to %s", source.name, len(batch.records), path.name)
        # Only after the batch is on disk is it safe to move the cursor past it.
        state.set(source.name, batch.cursor)
        cursor_after = batch.cursor

    summary = RunSummary(
        source=source.name,
        records=records,
        files=files,
        seconds=round(time.monotonic() - started, 2),
        cursor_before=cursor_before,
        cursor_after=cursor_after,
    )
    log.info("%s: %d records in %d files, %.1fs", source.name, records, files, summary.seconds)
    return summary


def _short(cursor: str | None, limit: int = 80) -> str:
    if cursor is None:
        return "<none>"
    return cursor if len(cursor) <= limit else cursor[: limit - 3] + "..."
