# nordlake

A small lakehouse on Norwegian open data. Python pulls sources into an append-only bronze
layer of Parquet files, dbt turns them into silver and gold tables on DuckDB, and Airflow
runs the whole thing nightly. Everything runs on a laptop and in CI with no services.

[![ci](https://github.com/r33hAB/nordlake/actions/workflows/ci.yml/badge.svg)](https://github.com/r33hAB/nordlake/actions/workflows/ci.yml)

```
  sources                 bronze (Parquet)          silver / gold (dbt on DuckDB)
  ─────────────────       ──────────────────        ───────────────────────────────
  Nav job feed      ──┐   data/bronze/<source>/     stg_nav_jobs ─────┬─ job_postings_daily
  Claude Code usage ──┼─▶   ingest_date=…/*.parquet ─▶                 └─ job_skill_mentions
  (your source)     ──┘   same 5 columns everywhere  stg_claude_messages ┬─ claude_cost_daily
                                                     stg_claude_prompts  └─ claude_sessions
         ▲                                                    ▲
         └──────────────── Airflow: nordlake_daily ───────────┘
```

## Sources

| Source | What | Where it comes from |
|---|---|---|
| `nav_jobs` | Every job ad on arbeidsplassen.nav.no, with full text for active ads | [Nav's public vacancy feed](https://navikt.github.io/pam-stilling-feed/), free to use under [these terms](https://arbeidsplassen.nav.no/vilkar-api) |
| `claude_transcripts` | Token usage and activity from Claude Code sessions, metadata only | `~/.claude/projects/**/*.jsonl` on your own machine |

Ads from Finn.no are not in Nav's feed, and Finn's terms prohibit crawling, so they are
out of scope. Named contact persons in ads are dropped before anything is written.

The transcript source never stores prompt text, model output or tool results, only ids,
timestamps, models and token counts ([ADR-0003](docs/adr/0003-transcripts-metadata-only.md)).
Pass `--hash-projects` to hide project directory names too.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv on first sync.

```sh
git clone https://github.com/r33hAB/nordlake && cd nordlake
make setup                       # uv sync
make demo                        # end to end on recorded fixtures, into demo-data/

make ingest                      # real data: last 14 days of Nav ads + your Claude transcripts
make dbt                         # seeds, models, tests -> data/nordlake.duckdb
make query SQL="select skill, sum(ads) ads from gold.job_skill_mentions group by 1 order by 2 desc limit 15"
```

The first Nav run fetches one request per active ad: about a minute per 1,000 ads, so the
default 14-day window takes 10 to 15 minutes. Later runs only read what changed.
`nordlake status` shows where each source is.

## What you get

| Table | Grain | Use |
|---|---|---|
| `silver.stg_nav_jobs` | one row per ad, latest version | title, employer, municipality, sector, occupation group, publish and expiry dates, description text |
| `gold.job_postings_daily` | day × sector × occupation group | how many ads and positions were published |
| `gold.job_skill_mentions` | week × occupation group × skill | which technologies ads ask for, from the `skills` seed |
| `silver.stg_claude_messages` | one row per API message | tokens in, cache write and read, tokens out, model, stop reason |
| `silver.stg_claude_prompts` | one row per prompt a person typed | activity, excluding tool results |
| `gold.claude_cost_daily` | day × project × model | spend at list price (`model_prices` seed) |
| `gold.claude_sessions` | one row per session | start, end, prompts, tool calls, cost |

```sql
-- which skills do IT ads ask for this month
select skill, sum(ads) as ads
from gold.job_skill_mentions
where occupation_level1 = 'IT' and week >= date_trunc('month', current_date)
group by 1 order by 2 desc;

-- what did Claude Code cost per project last week
select project, round(sum(cost_usd), 2) as usd, sum(messages) as messages
from gold.claude_cost_daily
where day >= current_date - 7
group by 1 order by 2 desc;
```

## Layout

```
src/nordlake/
  cli.py                 nordlake ingest | status | query | sources
  pipeline.py            runner: write batch to bronze, then advance the cursor
  storage.py             bronze writer, one Parquet file per batch, Hive-partitioned by ingest date
  state.py               one JSON cursor file per source
  sources/base.py        Record, Batch, Source protocol
  sources/nav_jobs.py    Nav feed adapter (+ a file-backed client for fixtures)
  sources/claude_transcripts.py
dbt/
  models/sources.yml     bronze tables read straight from Parquet
  models/silver/         staging: extract JSON, dedupe, price messages
  models/gold/           aggregates
  seeds/                 model_prices.csv, skills.csv
orchestration/airflow/dags/nordlake_daily.py
tests/                   unit tests + the fixtures that drive `make demo`
docs/adr/                why things are the way they are
```

## Adding a source

1. Write a class with a `name` and `fetch(cursor) -> Iterator[Batch]` (see `sources/base.py`).
   Yield records with a stable `key`, a timezone-aware `updated_at` and the raw object as `payload`.
   Put whatever you need to resume in the cursor string; the runner stores it after the batch is on disk.
2. Register the name in `sources/__init__.py` and construct it in `cli.make_source`.
3. Add the table to `dbt/models/sources.yml` and a `stg_<source>.sql` that extracts the columns
   and keeps the latest row per key.
4. Record a small fixture so the source runs in `make demo` without network.

Bronze never changes shape, so steps 1 and 3 are the whole job. The design is in
[ADR-0002](docs/adr/0002-source-adapters-and-append-only-bronze.md).

## Orchestration

`orchestration/airflow/dags/nordlake_daily.py` runs both ingests in parallel and then
`dbt build`, daily. `docker compose up` starts Airflow standalone with the repo mounted
at `/opt/nordlake` (first start installs the project into the image). The DAG only calls
the same CLI you run by hand, so there is one code path to debug.

## Roadmap

- Brønnøysundregistrene (company registry) and SSB Statbank as sources.
- Iceberg tables on MinIO for silver and gold, Trino as the shared query engine
  ([ADR-0001](docs/adr/0001-duckdb-and-parquet-first.md)).
- A data catalog with FAIR metadata generated from dbt's docs.
- Grafana dashboards on top of DuckDB.

## Licence

MIT.
