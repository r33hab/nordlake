# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com), newest first, grouped by date.

## 2026-10-15
### Added
- Ingest framework: source adapters yield batches with cursors, the runner lands them as append-only Parquet in bronze and advances the cursor afterwards.
- Source `nav_jobs`: Nav's public vacancy feed, paged with `If-Modified-Since` on first run, full ad fetched for active ads, contact lists dropped.
- Source `claude_transcripts`: metadata-only usage from Claude Code transcripts, byte-offset incremental reads, optional project-name hashing.
- dbt project on DuckDB: silver staging models with dedupe, cost model priced from a `model_prices` seed, gold aggregates for job postings, skill mentions, daily Claude spend and sessions, with schema tests.
- CLI `nordlake ingest|status|query|sources`, Makefile targets, and a fixture-driven `make demo` that CI runs end to end.
- Airflow DAG `nordlake_daily` and a docker-compose file for Airflow standalone.
- ADRs for the storage choice, the adapter protocol and the transcript privacy stance.
