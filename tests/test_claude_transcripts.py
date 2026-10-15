import json

from nordlake.sources.claude_transcripts import ClaudeTranscriptsSource


def _assistant(message_id: str, ts: str, text: str = "x", **usage) -> str:
    base_usage = {
        "input_tokens": 1,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 1,
    }
    return json.dumps(
        {
            "type": "assistant",
            "uuid": f"a-{message_id}-{text}",
            "timestamp": ts,
            "sessionId": "s1",
            "cwd": "/tmp/work/my-secret-project",
            "message": {
                "id": message_id,
                "model": "claude-opus-5-5",
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "usage": {**base_usage, **usage},
            },
        }
    )


def _user(uuid: str, ts: str) -> str:
    return json.dumps(
        {
            "type": "user",
            "uuid": uuid,
            "timestamp": ts,
            "sessionId": "s1",
            "cwd": "/tmp/work/my-secret-project",
            "message": {"role": "user", "content": "the actual prompt text"},
        }
    )


def test_fixture_transcripts_become_metadata_only_records(fixtures):
    source = ClaudeTranscriptsSource(projects_dir=fixtures / "claude_projects")
    records = [r for b in source.fetch(None) for r in b.records]

    keys = [r.key for r in records]
    assert keys.count("assistant:msg_0001") == 2, "one record per transcript line; silver dedupes"
    assert "user:u-0002" in keys, "tool results are kept, flagged, and filtered in silver"

    first = next(r for r in records if r.key == "assistant:msg_0001")
    assert first.payload["model"] == "claude-opus-5-5"
    assert first.payload["cache_write_5m_tokens"] == 5000
    assert first.payload["project"] == "sample-app"
    assert "content" not in first.payload
    assert "synthetic" not in json.dumps(first.payload), "message text never reaches bronze"
    assert first.payload["blocks"] == {"text": 1}

    tool_result = next(r for r in records if r.key == "user:u-0002")
    assert tool_result.payload["is_tool_result"] is True
    assert "actual" not in json.dumps(tool_result.payload)


def test_incomplete_last_line_is_left_for_the_next_run(tmp_path):
    project = tmp_path / "-tmp-work-my-secret-project"
    project.mkdir()
    transcript = project / "s1.jsonl"
    complete = (
        _user("u1", "2026-10-12T09:00:00Z") + "\n" + _assistant("m1", "2026-10-12T09:00:01Z") + "\n"
    )
    transcript.write_text(complete + '{"type":"assistant","uuid":"partial', encoding="utf-8")

    source = ClaudeTranscriptsSource(projects_dir=tmp_path)
    batches = list(source.fetch(None))
    records = [r for b in batches for r in b.records]

    assert [r.key for r in records] == ["user:u1", "assistant:m1"]
    offsets = json.loads(batches[-1].cursor)["files"]
    assert offsets[str(transcript)] == len(complete.encode("utf-8"))


def test_second_run_reads_only_appended_lines(tmp_path):
    project = tmp_path / "-tmp-work-my-secret-project"
    project.mkdir()
    transcript = project / "s1.jsonl"
    transcript.write_text(_assistant("m1", "2026-10-12T09:00:01Z") + "\n", encoding="utf-8")
    source = ClaudeTranscriptsSource(projects_dir=tmp_path)
    cursor = list(source.fetch(None))[-1].cursor

    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(_assistant("m2", "2026-10-12T09:05:00Z", output_tokens=7) + "\n")

    records = [r for b in source.fetch(cursor) for r in b.records]
    assert [r.key for r in records] == ["assistant:m2"]
    assert records[0].payload["output_tokens"] == 7


def test_truncated_file_restarts_from_zero(tmp_path):
    project = tmp_path / "-p"
    project.mkdir()
    transcript = project / "s1.jsonl"
    transcript.write_text(_assistant("m1", "2026-10-12T09:00:01Z") + "\n", encoding="utf-8")
    source = ClaudeTranscriptsSource(projects_dir=tmp_path)
    cursor = list(source.fetch(None))[-1].cursor

    transcript.write_text(_assistant("m9", "2026-10-12T10:00:01Z")[:10] + "\n", encoding="utf-8")
    records = [r for b in source.fetch(cursor) for r in b.records]
    assert records == [], "garbage line is skipped, not crashed on"


def test_hash_projects_hides_the_directory_name(tmp_path):
    project = tmp_path / "-p"
    project.mkdir()
    (project / "s1.jsonl").write_text(_user("u1", "2026-10-12T09:00:00Z") + "\n", encoding="utf-8")

    source = ClaudeTranscriptsSource(projects_dir=tmp_path, hash_projects=True)
    record = next(r for b in source.fetch(None) for r in b.records)
    assert record.payload["project"] != "my-secret-project"
    assert len(record.payload["project"]) == 12
