# ADR-0002: Sources are adapters that yield batches with cursors; bronze is append-only

Date: 2026-10-15. Status: accepted.

## Context

Every upstream system pages, filters and reports change differently. The platform
should make adding one a single file, and should survive a crash at any point without
losing or silently skipping data.

## Decision

A source implements `fetch(cursor) -> Iterator[Batch]`. A batch is a list of records plus
the cursor to persist once those records are on disk. The runner writes the batch to bronze
first and advances the cursor second. The cursor is an opaque string the source owns:
Nav's feed stores a page URL and a high-water timestamp, the transcript source stores a
byte offset per file.

Bronze is append-only: a record is `(source, key, updated_at, ingested_at, payload)` where
payload is the upstream object as a JSON string. Nothing is ever updated or deleted in
bronze. The silver layer in dbt keeps the latest version per key.

## Consequences

- A crash between write and cursor update replays one batch. Replays only add duplicate
  rows to bronze, which silver already handles, so the pipeline is safe to rerun at any time.
- Storage needs no per-source schema. The cost is that silver does JSON extraction, which
  DuckDB does quickly enough for this scale.
- A source can be tested with a fake client and no network (see `FileFeedClient`), and
  the same fixtures drive the end-to-end CI run.
