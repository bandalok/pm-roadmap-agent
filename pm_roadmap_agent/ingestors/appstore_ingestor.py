"""Apple App Store review ingestion via public Apple endpoints.

Two official, unauthenticated endpoints are used — no scraping, no hacks:
  1. iTunes Search API ``/lookup`` — resolves the numeric app id to the
     app's display name (used as the feedback source label).
  2. The customer-reviews RSS feed — Apple's public per-app review feed,
     paginated with ``page=N``. Each page holds up to 50 reviews.

Example feed URL:
    https://itunes.apple.com/us/rss/customerreviews/id=389801252/sortBy=mostRecent/xml

Notes / limits (documented here so users aren't surprised):
- Apple only exposes the ~500 most recent reviews this way.
- Ratings are 1-5 stars; ``created_at`` comes from the feed's ``<updated>``.
- The feed's first ``<entry>`` describes the app itself (no ``im:rating``)
  and is skipped.
"""

from __future__ import annotations

from typing import Iterable
from xml.etree import ElementTree as ET

import requests

from . import BaseIngestor

_LOOKUP_URL = "https://itunes.apple.com/lookup"
_FEED_URL = "https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/xml"
_FEED_PAGE_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews/page={page}"
    "/id={app_id}/sortBy=mostRecent/xml"
)

_ATOM_NS = "http://www.w3.org/2005/Atom"
_IM_NS = "http://itunes.apple.com/rss"


def _text(entry: ET.Element, tag: str, ns: str = _ATOM_NS) -> str | None:
    el = entry.find(f"{{{ns}}}{tag}")
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


class AppStoreIngestor(BaseIngestor):
    name = "appstore"

    def __init__(
        self,
        app_id: str | int,
        country: str = "us",
        max_pages: int = 5,
        timeout: int = 20,
    ):
        self.app_id = str(app_id)
        self.country = country.lower()
        self.max_pages = max(1, max_pages)
        self.timeout = timeout
        self._app_name: str | None = None

    @property
    def app_name(self) -> str:
        """Resolve once via the lookup API; fall back to the raw id."""
        if self._app_name is None:
            try:
                resp = requests.get(
                    _LOOKUP_URL,
                    params={"id": self.app_id, "country": self.country},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                self._app_name = results[0].get("trackName") if results else None
            except Exception:
                self._app_name = None
            if not self._app_name:
                self._app_name = f"app:{self.app_id}"
        return self._app_name

    def _fetch_page(self, page: int) -> list[dict]:
        url = (
            _FEED_URL.format(country=self.country, app_id=self.app_id)
            if page == 1
            else _FEED_PAGE_URL.format(country=self.country, app_id=self.app_id, page=page)
        )
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
            rating = _text(entry, "rating", _IM_NS)
            if rating is None:
                continue  # first entry describes the app, not a review
            title = _text(entry, "title") or ""
            body = _text(entry, "content") or ""
            text = f"{title}\n{body}".strip()
            if not text:
                continue
            try:
                rating_value = float(rating)
            except ValueError:
                rating_value = None
            review_id = _text(entry, "id")
            items.append(
                {
                    "id": None,  # generated at insert; feed ids are unstable
                    "source": f"appstore:{self.app_name}",
                    "source_id": review_id,
                    "text": text,
                    "author": _text(entry, "name", _IM_NS),
                    "rating": rating_value,
                    "created_at": _text(entry, "updated"),
                    "language": None,
                }
            )
        return items

    def fetch(self) -> Iterable[dict]:
        seen_empty = 0
        for page in range(1, self.max_pages + 1):
            try:
                items = self._fetch_page(page)
            except requests.RequestException:
                break  # network or HTTP error: keep what we have
            if not items:
                seen_empty += 1
                if seen_empty >= 2:
                    break
                continue
            yield from items
