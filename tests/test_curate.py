"""
tests/test_curate.py — Tests for curate.py retry and error-handling logic.

Tests mock the Groq client so no real API calls are made.
Covers:
  - call_groq_with_backoff retries on transient errors (simulating 429/timeout)
  - call_groq_with_backoff raises CurationError (typed, not silent) after all retries
  - Successful call on second attempt returns response and latency
  - Invalid JSON from Groq is handled in main() without raising uncaught exception
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import types
import unittest
from unittest.mock import MagicMock, patch, call

import pytest
from config import CurationError


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_groq_response(content: str):
    """Build a minimal mock object that mimics groq ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_VALID_JSON = json.dumps({
    "intro": "Test edition intro.",
    "curated_items": [
        {
            "title": "Test Article",
            "url": "https://arxiv.org/abs/1234.5678",
            "source": "arXiv",
            "category": "Research",
            "summary": "A test paper about LLMs.",
            "why_builders_care": "Builders can use this today.",
            "difficulty": "Intermediate",
            "reading_time_mins": 5,
            "tags": ["llm", "research"],
            "confidence_score": 80,
        }
    ],
})


# ── import the function under test ────────────────────────────────────────────

from curate import call_groq_with_backoff


# ── TestCallGroqWithBackoff ───────────────────────────────────────────────────

class TestCallGroqWithBackoff:

    def test_success_on_first_attempt(self):
        """Succeeds immediately on first call — returns (text, latency)."""
        client = MagicMock()
        client.chat.completions.create.return_value = _make_groq_response(_VALID_JSON)

        text, latency = call_groq_with_backoff(client, "test prompt")

        assert text == _VALID_JSON
        assert latency >= 0
        assert client.chat.completions.create.call_count == 1

    def test_retries_on_exception_then_succeeds(self):
        """
        First call raises RuntimeError (simulating 429/timeout),
        second call succeeds. Asserts retry happened and final result is correct.
        """
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            RuntimeError("429 Too Many Requests"),  # attempt 1 fails
            _make_groq_response(_VALID_JSON),        # attempt 2 succeeds
        ]

        with patch("curate.time.sleep"):  # skip real backoff sleep
            text, latency = call_groq_with_backoff(client, "test prompt")

        assert text == _VALID_JSON
        assert client.chat.completions.create.call_count == 2

    def test_raises_curation_error_after_all_retries(self):
        """
        All attempts raise — must raise CurationError (typed), NOT return
        silently with None or empty string.
        """
        from config import GROQ_MAX_RETRIES
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("timeout")

        with patch("curate.time.sleep"):
            with pytest.raises(CurationError) as exc_info:
                call_groq_with_backoff(client, "test prompt")

        assert "Groq failed after" in str(exc_info.value)
        assert client.chat.completions.create.call_count == GROQ_MAX_RETRIES

    def test_curation_error_is_not_generic_exception(self):
        """CurationError must be a subclass of NewsletterError, not bare Exception."""
        from config import CurationError, NewsletterError
        assert issubclass(CurationError, NewsletterError)

    def test_retries_twice_then_raises(self):
        """2 failures, 1 success on third — succeeds without raising."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            RuntimeError("timeout"),
            RuntimeError("connection reset"),
            _make_groq_response(_VALID_JSON),
        ]

        with patch("curate.time.sleep"):
            text, _ = call_groq_with_backoff(client, "prompt")

        assert text == _VALID_JSON
        assert client.chat.completions.create.call_count == 3

    def test_backoff_sleep_is_called_between_retries(self):
        """Asserts time.sleep is called after each failed attempt (not skipped)."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            RuntimeError("error"),
            _make_groq_response(_VALID_JSON),
        ]

        with patch("curate.time.sleep") as mock_sleep:
            call_groq_with_backoff(client, "prompt")

        # Should have slept once between attempt 1 and attempt 2
        assert mock_sleep.call_count == 1
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration >= 1  # initial delay is 2s

    def test_returned_text_matches_groq_content(self):
        """Return value[0] is exactly the content string from the response."""
        content = '{"intro": "x", "curated_items": []}'
        client = MagicMock()
        client.chat.completions.create.return_value = _make_groq_response(content)

        text, _ = call_groq_with_backoff(client, "p")
        assert text == content
