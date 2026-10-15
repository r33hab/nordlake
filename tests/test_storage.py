import json
from datetime import UTC, datetime, timedelta, timezone

import pyarrow.parquet as pq
import pytest

from nordlake.sources.base import Record
from nordlake.storage import BRONZE_SCHEMA, BronzeWriter


def test_record_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError):
        Record(key="k", updated_at=datetime(2026, 1, 1), payload={})


def test_write_lands_parquet_in_ingest_date_partition(tmp_path):
    writer = BronzeWriter(tmp_path / "bronze")
    oslo = timezone(timedelta(hours=2))
    records = [
        Record(
            key="a", updated_at=datetime(2026, 10, 10, 8, tzinfo=oslo), payload={"x": 1, "æ": "ø"}
        ),
        Record(key="b", updated_at=datetime(2026, 10, 10, 9, tzinfo=UTC), payload={"x": 2}),
    ]
    path = writer.write("demo", records)

    assert path is not None
    assert path.parent.name.startswith("ingest_date=")
    table = pq.read_table(path)
    assert table.schema.equals(BRONZE_SCHEMA)
    assert table.column("key").to_pylist() == ["a", "b"]
    # Local time is normalised to UTC on the way in.
    assert table.column("updated_at").to_pylist()[0] == datetime(2026, 10, 10, 6, tzinfo=UTC)
    assert json.loads(table.column("payload").to_pylist()[0]) == {"x": 1, "æ": "ø"}
    assert writer.files("demo") == [path]


def test_empty_batch_writes_nothing(tmp_path):
    writer = BronzeWriter(tmp_path / "bronze")
    assert writer.write("demo", []) is None
    assert writer.files("demo") == []
