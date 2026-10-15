from nordlake.state import StateStore


def test_missing_source_has_no_cursor(tmp_path):
    store = StateStore(tmp_path / "state")
    assert store.get("nav_jobs") is None
    assert store.describe("nav_jobs") == {"cursor": None, "updated_at": None}


def test_set_then_get_roundtrips_and_records_time(tmp_path):
    store = StateStore(tmp_path / "state")
    store.set("nav_jobs", '{"next_url": "/api/v1/feed/x"}')
    assert store.get("nav_jobs") == '{"next_url": "/api/v1/feed/x"}'
    assert store.describe("nav_jobs")["updated_at"] is not None
    assert not list((tmp_path / "state").glob("*.tmp")), "atomic write leaves no temp file"


def test_set_none_clears_cursor(tmp_path):
    store = StateStore(tmp_path / "state")
    store.set("s", "abc")
    store.set("s", None)
    assert store.get("s") is None
