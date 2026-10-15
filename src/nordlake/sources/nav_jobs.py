"""Job ads from Nav's public vacancy feed (arbeidsplassen.nav.no).

Docs: https://navikt.github.io/pam-stilling-feed/
Terms: https://arbeidsplassen.nav.no/vilkar-api (free to use; inactive ads must not be shown)

The feed is a linked list of pages, 1000 items each, ordered by last-modified time.
A page's `next_url` points to the following page, and the final page has `next_id: null`.
The first request can carry `If-Modified-Since` to skip history (the feed goes back to 2019).

Each feed item is only a stub (uuid, status, title, employer, municipality). The full ad,
including description and work locations, is one more request per item, so details are
fetched for ACTIVE items only. `contactList` is dropped before storage: it holds named
people with phone numbers and the platform has no use for it.

Cursor: JSON `{"next_url": "...", "last_modified": "..."}`. The last page is re-read on the
next run (new items land on it until it fills up), and items at or before `last_modified`
are skipped so a quiet feed produces no duplicate rows.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from nordlake.sources.base import Batch, Record

log = logging.getLogger(__name__)

BASE_URL = "https://pam-stilling-feed.nav.no"
PUBLIC_TOKEN_PATH = "/api/publicToken"
FEED_PATH = "/api/v1/feed"
USER_AGENT = "nordlake/0.1 (+https://github.com/r33hAB/nordlake)"
_JWT = re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")


class FeedClient(Protocol):
    def get(self, path: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        """GET a feed path. Returns the JSON body, or None on 304 Not Modified."""
        ...


class HttpFeedClient:
    """Talks to the real feed. Without an explicit token it picks up Nav's rotating public one."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._http = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        response = self._http.get(PUBLIC_TOKEN_PATH)
        response.raise_for_status()
        match = _JWT.search(response.text)
        if not match:
            raise RuntimeError("could not find a JWT in the public token response")
        self._token = match.group(0)
        log.info("nav_jobs: using Nav's public feed token")
        return self._token

    def get(self, path: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        token = self._ensure_token()
        response = self._http.get(
            path, headers={"Authorization": f"Bearer {token}", **(headers or {})}
        )
        if response.status_code == 304:
            return None
        response.raise_for_status()
        return response.json()


class FileFeedClient:
    """Serves a recorded feed from disk: `feed.json`, `feed/<id>.json`, `feedentry/<uuid>.json`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def get(self, path: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        relative = path.removeprefix("/api/v1/").strip("/")
        file = self.root / f"{relative}.json"
        if not file.exists():
            raise FileNotFoundError(f"no fixture for {path} (looked for {file})")
        return json.loads(file.read_text(encoding="utf-8"))


@dataclass
class NavJobsSource:
    client: FeedClient
    since_days: int = 14
    max_pages: int | None = None
    fetch_details: bool = True
    name: str = "nav_jobs"

    def fetch(self, cursor: str | None) -> Iterator[Batch]:
        state: dict[str, Any] = json.loads(cursor) if cursor else {}
        next_url: str = state.get("next_url") or FEED_PATH
        last_modified = _parse_dt(state.get("last_modified"))

        first_headers: dict[str, str] | None = None
        if not cursor:
            since = datetime.now(UTC) - timedelta(days=self.since_days)
            first_headers = {"If-Modified-Since": format_datetime(since, usegmt=True)}

        pages = 0
        while next_url:
            page = self.client.get(next_url, first_headers if pages == 0 else None)
            if page is None:  # 304, nothing new
                return
            pages += 1

            records: list[Record] = []
            high_water = last_modified
            for item in page.get("items", []):
                record = self._to_record(item, last_modified)
                if record is None:
                    continue
                records.append(record)
                if high_water is None or record.updated_at > high_water:
                    high_water = record.updated_at

            has_next = bool(page.get("next_id"))
            # When the feed ends, stay on this page: later runs re-read it for new items.
            resume_url = page.get("next_url") if has_next else (page.get("feed_url") or next_url)
            new_cursor = json.dumps(
                {
                    "next_url": resume_url,
                    "last_modified": high_water.isoformat() if high_water else None,
                }
            )
            log.info("nav_jobs: page %d -> %d new records", pages, len(records))
            yield Batch(records=records, cursor=new_cursor)

            last_modified = high_water
            if not has_next or (self.max_pages and pages >= self.max_pages):
                return
            next_url = page["next_url"]

    def _to_record(self, item: dict[str, Any], last_modified: datetime | None) -> Record | None:
        entry = item.get("_feed_entry") or {}
        key = entry.get("uuid") or item.get("id")
        modified = _parse_dt(item.get("date_modified") or entry.get("sistEndret"))
        if not key or modified is None:
            return None
        if last_modified is not None and modified <= last_modified:
            return None

        payload: dict[str, Any] = {
            "feed_item": {k: v for k, v in item.items() if k != "content_text"},
            "ad": None,
        }
        if self.fetch_details and entry.get("status") == "ACTIVE" and item.get("url"):
            detail = self.client.get(item["url"])
            payload["ad"] = _ad_content(detail) if detail else None
        return Record(key=key, updated_at=modified, payload=payload)


def _ad_content(detail: dict[str, Any]) -> dict[str, Any] | None:
    """The full ad sits under `ad_content` (older docs call it `json`), sometimes as a string."""
    raw = detail.get("ad_content", detail.get("json"))
    if raw is None:
        return None
    ad = json.loads(raw) if isinstance(raw, str) else dict(raw)
    ad.pop("contactList", None)
    return ad


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
