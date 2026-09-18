"""JSON ingestion — for API dumps and hand-rolled exports.

Expects a JSON file containing either a list of objects or an object with
an ``items``/``feedback``/``reviews`` list. Field names are configurable;
nested objects are not (keep exports flat).
"""

from __future__ import annotations

import json
from typing import Iterable

from . import BaseIngestor

_LIST_KEYS = ("items", "feedback", "reviews", "data")


class JSONIngestor(BaseIngestor):
    name = "json"

    def __init__(
        self,
        path: str,
        text_key: str = "text",
        id_key: str | None = None,
        author_key: str | None = None,
        rating_key: str | None = None,
        created_at_key: str | None = None,
        source_label: str | None = None,
    ):
        self.path = path
        self.text_key = text_key
        self.id_key = id_key
        self.author_key = author_key
        self.rating_key = rating_key
        self.created_at_key = created_at_key
        self.source_label = source_label or f"json:{path}"

    def _load(self) -> list[dict]:
        with open(self.path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            for key in _LIST_KEYS:
                if isinstance(payload.get(key), list):
                    return payload[key]
            raise ValueError(
                f"{self.path}: expected a list or an object with one of "
                f"{_LIST_KEYS}, got object keys {list(payload.keys())}"
            )
        if isinstance(payload, list):
            return payload
        raise ValueError(f"{self.path}: expected a JSON list or object")

    def fetch(self) -> Iterable[dict]:
        for obj in self._load():
            if not isinstance(obj, dict):
                continue
            text = obj.get(self.text_key)
            if not text or not str(text).strip():
                continue
            rating = obj.get(self.rating_key) if self.rating_key else None
            try:
                rating = float(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating = None
            yield {
                "id": str(obj.get(self.id_key)) if self.id_key and obj.get(self.id_key) else None,
                "source": self.source_label,
                "source_id": None,
                "text": str(text).strip(),
                "author": obj.get(self.author_key) if self.author_key else None,
                "rating": rating,
                "created_at": obj.get(self.created_at_key) if self.created_at_key else None,
                "language": obj.get("language"),
            }
