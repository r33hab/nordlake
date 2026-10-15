# ADR-0001: Parquet on a filesystem and DuckDB first, Iceberg and Trino later

Date: 2026-10-15. Status: accepted.

## Context

The platform should show the lakehouse pattern (raw files in object storage, SQL on top,
transformations as versioned code) without needing a cluster to run on a laptop or in CI.
The tools the pattern is usually built with in Norwegian public-sector job ads are dbt,
Airflow, Iceberg, Trino and Spark.

## Decision

- Bronze is plain Parquet on the local filesystem, Hive-partitioned by ingest date.
- dbt runs on DuckDB (`dbt-duckdb`) and reads bronze straight from the Parquet files.
- Iceberg table format, MinIO as S3-compatible storage, and Trino as a shared query engine
  are the next steps, not the first. The bronze layout (one directory per source, same
  five columns everywhere) is chosen so that step is a storage swap, not a redesign.

## Consequences

- `make demo` runs end to end in CI in under a minute with no services.
- DuckDB is single-process. Several people querying at once, or data beyond a laptop,
  is what the Trino step is for.
- Silver and gold are DuckDB tables inside one `.duckdb` file. When Iceberg arrives,
  dbt-duckdb can write those layers as Iceberg tables instead.
