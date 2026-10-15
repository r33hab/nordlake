import json

from nordlake.cli import main


def test_ingest_fixture_then_status(tmp_path, fixtures, capsys):
    data = tmp_path / "data"
    code = main(["--data-dir", str(data), "ingest", "nav_jobs", "--fixture", str(fixtures / "nav")])
    assert code == 0
    assert len(list((data / "bronze" / "nav_jobs").glob("ingest_date=*/*.parquet"))) == 2
    state = json.loads((data / "state" / "nav_jobs.json").read_text())
    assert json.loads(state["cursor"])["next_url"] == "/api/v1/feed/page-2"

    assert main(["--data-dir", str(data), "status"]) == 0
    out = capsys.readouterr().out
    assert "nav_jobs: 2 bronze files" in out
    assert "claude_transcripts: 0 bronze files" in out


def test_ingest_all_keeps_going_when_one_source_fails(tmp_path, fixtures):
    data = tmp_path / "data"
    code = main(
        [
            "--data-dir",
            str(data),
            "ingest",
            "all",
            "--fixture",
            str(tmp_path / "missing-fixture-dir"),
            "--projects-dir",
            str(fixtures / "claude_projects"),
        ]
    )
    assert code == 1, "nav_jobs failed on the missing fixture"
    assert (data / "bronze" / "claude_transcripts").exists(), "claude_transcripts still ran"


def test_query_without_database_fails_cleanly(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "query", "select 1"]) == 1
    assert "run `make dbt` first" in capsys.readouterr().err
