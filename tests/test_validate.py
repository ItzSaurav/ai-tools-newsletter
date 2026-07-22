"""Tests for validate.py — quality gate checks."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from validate import validate_items
from config import ValidationError


def _make_valid_item(**overrides) -> dict:
    """Return a fully valid curated item, with optional field overrides."""
    base = {
        "title": "A Great LLM Paper",
        "url": "https://arxiv.org/abs/1234.5678",
        "source": "arXiv",
        "category": "Research",
        "summary": "This paper presents a new architecture for large language models.",
        "why_builders_care": "Builders can use this technique to improve their fine-tuning pipeline.",
        "difficulty": "Intermediate",
        "reading_time_mins": 8,
        "tags": ["llm", "research"],
        "confidence_score": 80,
    }
    base.update(overrides)
    return base


def _make_valid_items(n: int = 4) -> list:
    return [
        _make_valid_item(
            title=f"Article {i}",
            url=f"https://example.com/{i}",
        )
        for i in range(n)
    ]


# ─────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────
class TestValidHappyPath:
    def test_valid_items_no_error(self):
        items = _make_valid_items(5)
        validate_items(items)  # should not raise

    def test_minimum_items_exactly(self):
        validate_items(_make_valid_items(3))  # MIN_ITEMS = 3


# ─────────────────────────────────────────────
# Too few items
# ─────────────────────────────────────────────
class TestTooFewItems:
    def test_empty_list_raises(self):
        with pytest.raises(ValidationError, match="Too few curated items"):
            validate_items([])

    def test_two_items_raises(self):
        with pytest.raises(ValidationError, match="Too few curated items"):
            validate_items(_make_valid_items(2))


# ─────────────────────────────────────────────
# Required fields
# ─────────────────────────────────────────────
class TestRequiredFields:
    def test_missing_title(self):
        items = _make_valid_items(4)
        items[0]["title"] = ""
        with pytest.raises(ValidationError, match="missing required field 'title'"):
            validate_items(items)

    def test_missing_url(self):
        items = _make_valid_items(4)
        items[1]["url"] = ""
        with pytest.raises(ValidationError, match="missing required field 'url'"):
            validate_items(items)

    def test_missing_summary(self):
        items = _make_valid_items(4)
        items[0]["summary"] = "   "
        with pytest.raises(ValidationError, match="missing required field 'summary'"):
            validate_items(items)

    def test_missing_why_builders_care(self):
        items = _make_valid_items(4)
        items[0]["why_builders_care"] = ""
        with pytest.raises(ValidationError, match="missing required field 'why_builders_care'"):
            validate_items(items)


# ─────────────────────────────────────────────
# URL format
# ─────────────────────────────────────────────
class TestURLFormat:
    def test_non_http_url_raises(self):
        items = _make_valid_items(4)
        items[0]["url"] = "ftp://bad-protocol.com"
        with pytest.raises(ValidationError, match="URL does not start with 'http'"):
            validate_items(items)


# ─────────────────────────────────────────────
# Duplicates
# ─────────────────────────────────────────────
class TestDuplicates:
    def test_duplicate_url_raises(self):
        items = _make_valid_items(4)
        items[1]["url"] = items[0]["url"]
        with pytest.raises(ValidationError, match="duplicate URL detected"):
            validate_items(items)

    def test_duplicate_title_raises(self):
        items = _make_valid_items(4)
        items[2]["title"] = items[0]["title"]
        with pytest.raises(ValidationError, match="duplicate title detected"):
            validate_items(items)


# ─────────────────────────────────────────────
# Difficulty
# ─────────────────────────────────────────────
class TestDifficulty:
    def test_invalid_difficulty_raises(self):
        items = _make_valid_items(4)
        items[0]["difficulty"] = "Expert"  # not in allowed set
        with pytest.raises(ValidationError, match="invalid difficulty"):
            validate_items(items)

    def test_valid_difficulties_pass(self):
        for diff in ("Beginner", "Intermediate", "Advanced"):
            items = _make_valid_items(4)
            for it in items:
                it["difficulty"] = diff
            validate_items(items)  # should not raise


# ─────────────────────────────────────────────
# Confidence score
# ─────────────────────────────────────────────
class TestConfidenceScore:
    def test_out_of_range_high(self):
        items = _make_valid_items(4)
        items[0]["confidence_score"] = 150
        with pytest.raises(ValidationError, match="out of range"):
            validate_items(items)

    def test_out_of_range_low(self):
        items = _make_valid_items(4)
        items[0]["confidence_score"] = -10
        with pytest.raises(ValidationError, match="out of range"):
            validate_items(items)

    def test_none_confidence_passes(self):
        items = _make_valid_items(4)
        items[0]["confidence_score"] = None
        # None means Groq omitted it — should not raise
        validate_items(items)
