import json

import httpx

from nordlake.sources.nav_jobs import FileFeedClient, HttpFeedClient, NavJobsSource

AD_1 = "11111111-1111-4111-8111-111111111111"
AD_2 = "22222222-2222-4222-8222-222222222222"
AD_3 = "33333333-3333-4333-8333-333333333333"


class CountingClient:
    def __init__(self, inner):
        self.inner = inner
        self.calls: list[str] = []

    def get(self, path, headers=None):
        self.calls.append(path)
        return self.inner.get(path, headers)


def test_walks_pages_and_fetches_details_for_active_ads_only(fixtures):
    client = CountingClient(FileFeedClient(fixtures / "nav"))
    source = NavJobsSource(client=client)

    batches = list(source.fetch(None))
    records = [r for b in batches for r in b.records]

    assert len(batches) == 2, "one batch per feed page"
    assert [r.key for r in records] == [AD_1, AD_2, AD_3]
    assert records[0].payload["ad"]["title"] == "Senior backendutvikler"
    assert "contactList" not in records[0].payload["ad"], "named contacts are dropped"
    assert records[1].payload["ad"] is None, "inactive ads keep only the feed stub"
    assert "content_text" not in records[0].payload["feed_item"]
    assert client.calls == [
        "/api/v1/feed",
        f"/api/v1/feedentry/{AD_1}",
        "/api/v1/feed/page-2",
        f"/api/v1/feedentry/{AD_3}",
    ]

    cursor = json.loads(batches[-1].cursor)
    assert cursor == {
        "next_url": "/api/v1/feed/page-2",
        "last_modified": "2026-10-11T10:00:00+02:00",
    }


def test_second_run_rereads_last_page_but_yields_nothing_new(fixtures):
    source = NavJobsSource(client=FileFeedClient(fixtures / "nav"))
    cursor = list(source.fetch(None))[-1].cursor

    batches = list(source.fetch(cursor))

    assert len(batches) == 1
    assert batches[0].records == []
    assert json.loads(batches[0].cursor) == json.loads(cursor)


def test_max_pages_stops_after_the_limit(fixtures):
    source = NavJobsSource(client=FileFeedClient(fixtures / "nav"), max_pages=1)
    batches = list(source.fetch(None))
    assert len(batches) == 1
    assert json.loads(batches[0].cursor)["next_url"] == "/api/v1/feed/page-2"


def test_no_details_never_calls_feedentry(fixtures):
    client = CountingClient(FileFeedClient(fixtures / "nav"))
    source = NavJobsSource(client=client, fetch_details=False)
    records = [r for b in source.fetch(None) for r in b.records]
    assert all(r.payload["ad"] is None for r in records)
    assert not any("feedentry" in call for call in client.calls)


def test_http_client_picks_up_public_token_and_sends_bearer(fixtures):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/publicToken":
            return httpx.Response(
                200,
                text="Current public token:\n" + ".".join(["abcdefghijklmnopqrstuvwx"] * 3) + "\n",
            )
        if request.url.path == "/api/v1/feed":
            return httpx.Response(
                200, json=json.loads((fixtures / "nav" / "feed.json").read_text())
            )
        return httpx.Response(404)

    http = httpx.Client(base_url="https://feed.test", transport=httpx.MockTransport(handler))
    client = HttpFeedClient(client=http)

    page = client.get(
        "/api/v1/feed", headers={"If-Modified-Since": "Sat, 01 Jan 2026 00:00:00 GMT"}
    )

    assert page["id"] == "page-1"
    assert [r.url.path for r in seen] == ["/api/publicToken", "/api/v1/feed"]
    assert seen[1].headers["Authorization"].startswith("Bearer abcdefghijklmnopqrstuvwx.")
    assert seen[1].headers["If-Modified-Since"] == "Sat, 01 Jan 2026 00:00:00 GMT"


def test_http_client_returns_none_on_not_modified():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304)

    http = httpx.Client(base_url="https://feed.test", transport=httpx.MockTransport(handler))
    client = HttpFeedClient(client=http, token="t")
    assert client.get("/api/v1/feed") is None
