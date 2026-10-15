"""Command-line entry point: `nordlake ingest|status|query|sources`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from nordlake.config import Settings
from nordlake.pipeline import run_source
from nordlake.sources import SOURCE_NAMES
from nordlake.sources.base import Source
from nordlake.state import StateStore
from nordlake.storage import BronzeWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nordlake", description="Ingest sources into the bronze layer."
    )
    parser.add_argument(
        "--data-dir", help="root for bronze/, state/ and the DuckDB file (env NORDLAKE_DATA_DIR)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="pull new records from one source, or all of them")
    ingest.add_argument("source", choices=(*SOURCE_NAMES, "all"))
    ingest.add_argument(
        "--since-days", type=int, default=14, help="nav_jobs: history window on the first run"
    )
    ingest.add_argument("--max-pages", type=int, help="nav_jobs: stop after this many feed pages")
    ingest.add_argument(
        "--no-details", action="store_true", help="nav_jobs: skip the per-ad detail request"
    )
    ingest.add_argument(
        "--fixture", type=Path, help="nav_jobs: read a recorded feed from this directory"
    )
    ingest.add_argument(
        "--nav-token", help="nav_jobs: private feed token (default: Nav's public token)"
    )
    ingest.add_argument(
        "--projects-dir",
        type=Path,
        help="claude_transcripts: transcript root (default ~/.claude/projects)",
    )
    ingest.add_argument(
        "--hash-projects",
        action="store_true",
        help="claude_transcripts: store a hash instead of the project name",
    )

    commands.add_parser("status", help="show cursors and bronze file counts")
    commands.add_parser("sources", help="list registered sources")

    query = commands.add_parser("query", help="run SQL against the DuckDB file dbt builds")
    query.add_argument("sql")
    query.add_argument("--limit", type=int, default=50)
    return parser


def make_source(name: str, args: argparse.Namespace) -> Source:
    if name == "nav_jobs":
        from nordlake.sources.nav_jobs import FileFeedClient, HttpFeedClient, NavJobsSource

        client = (
            FileFeedClient(args.fixture) if args.fixture else HttpFeedClient(token=args.nav_token)
        )
        return NavJobsSource(
            client=client,
            since_days=args.since_days,
            max_pages=args.max_pages,
            fetch_details=not args.no_details,
        )
    if name == "claude_transcripts":
        from nordlake.sources.claude_transcripts import ClaudeTranscriptsSource

        kwargs = {"hash_projects": args.hash_projects}
        if args.projects_dir:
            kwargs["projects_dir"] = args.projects_dir
        return ClaudeTranscriptsSource(**kwargs)
    raise ValueError(f"unknown source {name}")


def cmd_ingest(settings: Settings, args: argparse.Namespace) -> int:
    names = SOURCE_NAMES if args.source == "all" else (args.source,)
    state = StateStore(settings.state_dir)
    writer = BronzeWriter(settings.bronze_dir)
    failures = 0
    for name in names:
        try:
            summary = run_source(make_source(name, args), state, writer)
        except Exception:  # keep going with the other sources, report at the end
            logging.getLogger(name).exception("ingest failed")
            failures += 1
            continue
        s = summary
        print(f"{s.source}: {s.records} records, {s.files} files, {s.seconds}s")
    return 1 if failures else 0


def cmd_status(settings: Settings, args: argparse.Namespace) -> int:
    state = StateStore(settings.state_dir)
    writer = BronzeWriter(settings.bronze_dir)
    print(f"data dir: {settings.data_dir}")
    for name in SOURCE_NAMES:
        info = state.describe(name)
        files = writer.files(name)
        cursor = info.get("cursor")
        shown = (
            cursor
            if cursor and len(cursor) <= 100
            else (cursor[:97] + "..." if cursor else "<none>")
        )
        print(f"- {name}: {len(files)} bronze files, last run {info.get('updated_at') or 'never'}")
        print(f"    cursor: {shown}")
    return 0


def cmd_query(settings: Settings, args: argparse.Namespace) -> int:
    import duckdb

    if not settings.duckdb_path.exists():
        print(f"no database at {settings.duckdb_path}; run `make dbt` first", file=sys.stderr)
        return 1
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        result = con.sql(args.sql)
        rows = result.fetchmany(args.limit)
        columns = result.columns
    widths = [
        max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
        for i, c in enumerate(columns)
    ]
    print("  ".join(str(c).ljust(w) for c, w in zip(columns, widths, strict=True)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))
    return 0


def cmd_sources(settings: Settings, args: argparse.Namespace) -> int:
    print(json.dumps(list(SOURCE_NAMES)))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    settings = Settings.from_env(args.data_dir)
    handler = {
        "ingest": cmd_ingest,
        "status": cmd_status,
        "query": cmd_query,
        "sources": cmd_sources,
    }[args.command]
    return handler(settings, args)


if __name__ == "__main__":
    sys.exit(main())
