"""Paths and environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def duckdb_path(self) -> Path:
        return Path(os.environ.get("NORDLAKE_DUCKDB", self.data_dir / "nordlake.duckdb"))

    @classmethod
    def from_env(cls, data_dir: str | os.PathLike[str] | None = None) -> Settings:
        raw = data_dir or os.environ.get("NORDLAKE_DATA_DIR", "data")
        return cls(data_dir=Path(raw).expanduser().resolve())
