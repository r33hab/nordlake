"""Source registry. Add a source here and it shows up in the CLI."""

from __future__ import annotations

from nordlake.sources.base import Batch, Record, Source

SOURCE_NAMES: tuple[str, ...] = ("nav_jobs", "claude_transcripts")

__all__ = ["SOURCE_NAMES", "Batch", "Record", "Source"]
