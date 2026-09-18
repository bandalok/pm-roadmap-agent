"""Tests for defensive JSON extraction from model output."""

import pytest

from pm_roadmap_agent.agents.parsing import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('[1, 2]') == [1, 2]


def test_markdown_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```\n[1]\n```') == [1]


def test_preamble_and_trailing_text():
    out = 'Here is the result:\n{"themes": ["x"]}\nHope this helps!'
    assert extract_json(out) == {"themes": ["x"]}


def test_nested_braces_in_strings():
    out = '{"label": "a { tricky } label", "n": 2}'
    assert extract_json(out) == {"label": "a { tricky } label", "n": 2}


def test_unparseable_raises():
    with pytest.raises(ValueError):
        extract_json("no json here at all")
