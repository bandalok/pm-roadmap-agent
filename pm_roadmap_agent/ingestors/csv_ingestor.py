"""CSV ingestion — the universal escape hatch.

Almost every feedback tool (App Store Connect, Intercom, Zendesk, survey
tools) exports CSV, so this ingestor is deliberately configurable: point it
at the file and name the columns. ``text_column`` is the only required one.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from . import BaseIngestor


class CSVIngestor(BaseIngestor):
    name = "csv"

    def __init__(
        self,
        path: str,
        text_column: str = "text",
        id_column: str | None = None,
        author_column: str | None = None,
        rating_column: str | None = None,
        created_at_column: str | None = None,
        source_label: str | None = None,
    ):
        self.path = path
        self.text_column = text_column
        self.id_column = id_column
        self.author_column = author_column
        self.rating_column = rating_column
        self.created_at_column = created_at_column
        self.source_label = source_label or f"csv:{path}"

    def _cell(self, row: pd.Series, column: str | None):
        if not column or column not in row or pd.isna(row[column]):
            return None
        return row[column]

    def fetch(self) -> Iterable[dict]:
        df = pd.read_csv(self.path)
        if self.text_column not in df.columns:
            raise ValueError(
                f"Column {self.text_column!r} not found in {self.path}. "
                f"Available: {list(df.columns)}"
            )
        for _, row in df.iterrows():
            text = self._cell(row, self.text_column)
            if text is None or not str(text).strip():
                continue
            rating = self._cell(row, self.rating_column)
            try:
                rating = float(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating = None
            created = self._cell(row, self.created_at_column)
            yield {
                "id": str(self._cell(row, self.id_column)) if self.id_column else None,
                "source": self.source_label,
                "source_id": None,
                "text": str(text).strip(),
                "author": self._cell(row, self.author_column),
                "rating": rating,
                "created_at": str(created) if created is not None else None,
                "language": None,
            }
