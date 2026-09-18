"""Feedback ingestors — one per source, one shared output shape.

Every ingestor yields plain dicts with these keys (all optional except
``text``):
    id, source, source_id, text, author, rating, created_at (ISO string),
    language

Keeping ingestion dumb and uniform means the rest of the pipeline never
cares where feedback came from — which is exactly what lets a PM add a
new source (Intercom, Discourse, G2...) by writing one small class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class BaseIngestor(ABC):
    name = "base"

    @abstractmethod
    def fetch(self) -> Iterable[dict]:
        """Yield normalized feedback dicts."""
        raise NotImplementedError
