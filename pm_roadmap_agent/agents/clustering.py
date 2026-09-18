"""Theme-clustering agent (LLM-backed).

Pipeline inside the agent:
  1. Batch feedback (context windows are finite; ``cluster_batch_size``
     controls the trade-off between coherence and cost).
  2. Ask the model to affinity-map each batch into themes, referencing
     feedback by stable database id (never by position — positions shift).
  3. Merge the per-batch theme lists into one canonical set, so "app
     crashes" from batch 1 and "stability issues" from batch 2 become a
     single theme downstream. Trends and RICE scores are only meaningful
     on stable, long-lived themes.

The agent is deliberately strict about ids: any feedback id the model
invents is dropped, and items the model forgets are swept into an
"Uncategorized" theme. A clustering pass must never silently lose
evidence.
"""

from __future__ import annotations

import uuid

from .. import prompts
from ..llm.base import LLMProvider
from .parsing import extract_json


def _sanitize_batch_themes(raw_themes, valid_ids: set[str]) -> list[dict]:
    """Keep only well-formed themes referencing real feedback ids."""
    clean = []
    for theme in raw_themes:
        if not isinstance(theme, dict):
            continue
        label = str(theme.get("label", "")).strip()
        if not label:
            continue
        ids = [fid for fid in theme.get("feedback_ids", []) if fid in valid_ids]
        if not ids:
            continue
        quotes = [str(q).strip() for q in theme.get("quotes", []) if str(q).strip()][:2]
        clean.append(
            {
                "label": label,
                "description": str(theme.get("description", "")).strip(),
                "feedback_ids": ids,
                "quotes": quotes,
            }
        )
    return clean


def cluster_themes(
    feedback: list[dict],
    provider: LLMProvider,
    *,
    batch_size: int = 40,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> list[dict]:
    """Cluster feedback into merged themes. Returns theme dicts ready for
    ``Store.save_themes`` (each with label, description, feedback_ids, quotes).
    """
    if not feedback:
        return []

    valid_ids = {item["id"] for item in feedback}
    assigned: set[str] = set()
    batch_themes: list[dict] = []

    for start in range(0, len(feedback), batch_size):
        batch = feedback[start : start + batch_size]
        prompt = prompts.cluster_prompt(batch)
        raw = provider.complete(
            prompt,
            system=prompts.CLUSTER_SYSTEM,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        parsed = extract_json(raw)
        if not isinstance(parsed, list):
            raise ValueError("Clustering model did not return a JSON array")
        clean = _sanitize_batch_themes(parsed, valid_ids)
        for theme in clean:
            assigned.update(theme["feedback_ids"])
        batch_themes.extend(clean)

    # Merge across batches into canonical themes.
    merged = _merge_themes(batch_themes, provider, max_tokens, temperature)

    # Sweep anything the model dropped into "Uncategorized" so no feedback
    # is silently lost.
    merged_ids: set[str] = set()
    for theme in merged:
        merged_ids.update(theme["feedback_ids"])
    orphaned = [fid for fid in valid_ids if fid not in merged_ids]
    if orphaned:
        merged.append(
            {
                "id": f"th_{uuid.uuid4().hex[:12]}",
                "label": "Other / uncategorized",
                "description": "Feedback items that did not fit a named theme.",
                "feedback_ids": sorted(orphaned),
                "quotes": [],
            }
        )
    # Carry the pre-merge label mapping for provenance.
    for theme in merged:
        theme.setdefault("id", f"th_{uuid.uuid4().hex[:12]}")
    return merged


def _merge_themes(
    batch_themes: list[dict],
    provider: LLMProvider,
    max_tokens: int,
    temperature: float,
) -> list[dict]:
    if not batch_themes:
        return []
    if len(batch_themes) == 1:
        single = dict(batch_themes[0])
        single["id"] = f"th_{uuid.uuid4().hex[:12]}"
        return [single]

    prompt = prompts.merge_prompt(batch_themes)
    raw = provider.complete(
        prompt,
        system=prompts.MERGE_SYSTEM,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
    )
    parsed = extract_json(raw)
    if not isinstance(parsed, list):
        raise ValueError("Merge model did not return a JSON array")

    # Map merged themes back to feedback ids via their source labels.
    by_label: dict[str, list[str]] = {}
    for theme in batch_themes:
        by_label.setdefault(theme["label"], []).extend(theme["feedback_ids"])

    merged: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict) or not str(item.get("label", "")).strip():
            continue
        ids: list[str] = []
        for source_label in item.get("source_labels", []):
            ids.extend(by_label.get(str(source_label), []))
        # Dedupe while preserving order.
        seen: set[str] = set()
        unique_ids = [fid for fid in ids if not (fid in seen or seen.add(fid))]
        if not unique_ids:
            continue
        merged.append(
            {
                "id": f"th_{uuid.uuid4().hex[:12]}",
                "label": str(item["label"]).strip(),
                "description": str(item.get("description", "")).strip(),
                "feedback_ids": unique_ids,
                "quotes": [str(q).strip() for q in item.get("quotes", []) if str(q).strip()][
                    :2
                ],
            }
        )
    return merged
