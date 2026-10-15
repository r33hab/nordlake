"""Bronze layer: append-only Parquet, one directory per source, partitioned by ingest date.

The schema is the same for every source. The upstream object lives in `payload`
as a JSON string, so adding a source never means touching storage; the silver
layer in dbt is where source-specific columns are pulled out.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from nordlake.sources.base import Record

BRONZE_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("key", pa.string(), nullable=False),
        pa.field("updated_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("payload", pa.string(), nullable=False),
    ]
)


class BronzeWriter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, source: str, records: list[Record]) -> Path | None:
        """Write one Parquet file for the batch. Returns None when there is nothing to write."""
        if not records:
            return None
        now = datetime.now(UTC)
        partition = self.root / source / f"ingest_date={now:%Y-%m-%d}"
        partition.mkdir(parents=True, exist_ok=True)
        path = partition / f"{now:%H%M%S}-{uuid.uuid4().hex[:8]}.parquet"

        table = pa.table(
            {
                "source": [source] * len(records),
                "key": [r.key for r in records],
                "updated_at": [r.updated_at.astimezone(UTC) for r in records],
                "ingested_at": [now] * len(records),
                "payload": [
                    json.dumps(r.payload, ensure_ascii=False, default=str) for r in records
                ],
            },
            schema=BRONZE_SCHEMA,
        )
        pq.write_table(table, path, compression="zstd")
        return path

    def files(self, source: str) -> list[Path]:
        root = self.root / source
        if not root.exists():
            return []
        return sorted(root.glob("ingest_date=*/*.parquet"))
