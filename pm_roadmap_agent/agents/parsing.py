"""Defensive JSON extraction from LLM responses.

Models usually comply with "respond with a single JSON value", but not
always: markdown fences, a sentence of preamble, or a trailing apology
all happen in practice. This module recovers the JSON payload instead of
crashing the pipeline — a small reliability habit that matters a lot in
an agentic system where one malformed response shouldn't kill a run.
"""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str):
    """Pull the first JSON value out of free-form model output."""
    cleaned = text.strip()
    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    # Fast path: the whole thing is JSON.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Slow path: find the first balanced {...} or [...] span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"Could not extract JSON from model output: {text[:200]!r}")
