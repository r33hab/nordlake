"""The contract every source adapter implements.

A source turns an upstream system into an iterator of batches. Each batch carries
the records to append to the bronze layer and the cursor to persist once those
records are safely on disk. A source never writes files and never touches state:
the runner does both, in that order, so a crash between the two can only ever
replay a batch, never lose one. Bronze is append-only, and the silver layer
deduplicates by key, so replays are harmless.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Record:
    """One upstream object, as raw as the source can keep it."""

    key: str
    updated_at: datetime
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if self.updated_at.tzinfo is None:
            raise ValueError(f"record {self.key}: updated_at must be timezone-aware")


@dataclass
class Batch:
    records: list[Record] = field(default_factory=list)
    cursor: str | None = None


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self, cursor: str | None) -> Iterator[Batch]:
        """Yield batches, starting after `cursor` (None means from the beginning)."""
        ...
