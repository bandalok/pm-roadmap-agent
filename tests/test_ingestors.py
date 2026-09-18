"""Tests for feedback ingestors (CSV, JSON, App Store)."""

import os

import pytest

from pm_roadmap_agent.ingestors import appstore_ingestor as appstore_mod
from pm_roadmap_agent.ingestors.appstore_ingestor import AppStoreIngestor
from pm_roadmap_agent.ingestors.csv_ingestor import CSVIngestor
from pm_roadmap_agent.ingestors.json_ingestor import JSONIngestor

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_csv_ingestor():
    ingestor = CSVIngestor(
        os.path.join(FIXTURES, "sample.csv"),
        text_column="text",
        author_column="author",
        rating_column="rating",
        created_at_column="created_at",
    )
    items = list(ingestor.fetch())
    assert len(items) == 3
    assert items[0]["text"] == "The app crashed on launch today"
    assert items[0]["rating"] == 1.0
    assert items[0]["author"] == "amy"
    assert items[0]["created_at"].startswith("2026-09-01")


def test_csv_ingestor_missing_text_column():
    ingestor = CSVIngestor(os.path.join(FIXTURES, "sample.csv"), text_column="nope")
    with pytest.raises(ValueError, match="nope"):
        list(ingestor.fetch())


def test_json_ingestor():
    ingestor = JSONIngestor(
        os.path.join(FIXTURES, "sample.json"),
        text_key="text",
        author_key="author",
        rating_key="rating",
        created_at_key="created_at",
    )
    items = list(ingestor.fetch())
    assert len(items) == 2
    assert items[1]["text"] == "Please add a sleep timer feature"
    assert items[1]["rating"] == 4.0


class _FakeResponse:
    def __init__(self, content=None, payload=None):
        self.content = content
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_get(url, params=None, timeout=None):
    if "lookup" in url:
        return _FakeResponse(payload={"results": [{"trackName": "Test App"}]})
    with open(os.path.join(FIXTURES, "appstore_feed.xml"), "rb") as fh:
        return _FakeResponse(content=fh.read())


def test_appstore_ingestor(monkeypatch):
    monkeypatch.setattr(appstore_mod.requests, "get", _fake_get)
    ingestor = AppStoreIngestor(app_id=123456, country="us", max_pages=1)
    assert ingestor.app_name == "Test App"
    items = list(ingestor.fetch())
    # The first feed entry describes the app (no rating) and is skipped.
    assert len(items) == 2
    assert items[0]["rating"] == 1.0
    assert "crashed three times" in items[0]["text"]
    assert items[0]["author"] == "reviewer_one"
    assert items[0]["source"] == "appstore:Test App"
    assert items[1]["rating"] == 5.0
