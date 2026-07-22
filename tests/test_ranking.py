"""Tests for ranking.py — scoring, deduplication, and keyword density."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ranking import (
    score_article,
    rank_articles,
    _source_score,
    _hn_score,
    _github_score,
    _recency_score,
    _keyword_score,
    _reject_penalty,
)


# ─────────────────────────────────────────────
# Source score
# ─────────────────────────────────────────────
class TestSourceScore:
    def test_high_trust_source(self):
        assert _source_score("arXiv") == 9.0

    def test_known_source_case_insensitive(self):
        assert _source_score("hacker news") == 8.0

    def test_partial_match(self):
        score = _source_score("GitHub Trending")
        assert score > 0

    def test_unknown_source_defaults(self):
        assert _source_score("Unknown Blog XYZ") == 5.0


# ─────────────────────────────────────────────
# HN score
# ─────────────────────────────────────────────
class TestHNScore:
    def test_zero_points(self):
        assert _hn_score(0) == 0.0

    def test_negative_points(self):
        assert _hn_score(-5) == 0.0

    def test_high_points_capped(self):
        assert _hn_score(10_000) == 10.0

    def test_moderate_points(self):
        score = _hn_score(100)
        assert 0 < score < 10


# ─────────────────────────────────────────────
# GitHub score
# ─────────────────────────────────────────────
class TestGitHubScore:
    def test_zero_stars(self):
        assert _github_score(0, 0) == 0.0

    def test_high_stars_capped(self):
        assert _github_score(100_000, 50_000) == 10.0

    def test_forks_weighted_half(self):
        s1 = _github_score(100, 0)
        s2 = _github_score(0, 200)
        assert abs(s1 - s2) < 0.5  # forks*0.5 ≈ same contribution as stars


# ─────────────────────────────────────────────
# Recency score
# ─────────────────────────────────────────────
class TestRecencyScore:
    def test_fresh_article(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        fresh = (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _recency_score(fresh) == 10.0

    def test_week_old_article(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        old = (now - datetime.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _recency_score(old) == 5.0

    def test_empty_date_returns_neutral(self):
        score = _recency_score("")
        assert score == 3.0

    def test_very_old_article(self):
        assert _recency_score("2020-01-01") == 0.0


# ─────────────────────────────────────────────
# Keyword score
# ─────────────────────────────────────────────
class TestKeywordScore:
    def test_no_keywords(self):
        assert _keyword_score("Cooking recipe for pasta", "Best pasta sauce ever") == 0.0

    def test_llm_in_title(self):
        score = _keyword_score("New LLM released by Anthropic", "")
        assert score > 0

    def test_multiple_keywords(self):
        score = _keyword_score(
            "RAG with vLLM and LangChain agent",
            "vector database inference optimization"
        )
        assert score > 5.0

    def test_capped_at_10(self):
        long_text = " ".join(["llm agent rag vector inference vllm cuda benchmark"] * 10)
        assert _keyword_score(long_text, long_text) == 10.0


# ─────────────────────────────────────────────
# Reject penalty
# ─────────────────────────────────────────────
class TestRejectPenalty:
    def test_no_reject_keywords(self):
        assert _reject_penalty("New LLM from OpenAI", "Fast inference engine") == 0.0

    def test_crypto_penalized(self):
        assert _reject_penalty("Bitcoin price analysis", "cryptocurrency market") < 0

    def test_politics_penalized(self):
        assert _reject_penalty("Election results 2024", "politics news") < 0


# ─────────────────────────────────────────────
# Composite score
# ─────────────────────────────────────────────
class TestScoreArticle:
    def test_returns_float_in_range(self):
        article = {
            "title": "New LLM from Anthropic",
            "url": "https://example.com",
            "source": "arXiv",
            "summary_raw": "Researchers present a new large language model with RAG capabilities.",
            "date": "",
            "hn_points": 0,
            "github_stars": 0,
            "github_forks": 0,
        }
        score = score_article(article)
        assert 0 <= score <= 100

    def test_crypto_article_scores_lower(self):
        ai_article = {
            "title": "LLM with RAG and agents", "url": "https://a.com",
            "source": "arXiv", "summary_raw": "inference vllm cuda",
            "date": "", "hn_points": 500, "github_stars": 1000, "github_forks": 200,
        }
        crypto_article = {
            "title": "Bitcoin price crashes", "url": "https://b.com",
            "source": "Unknown Blog", "summary_raw": "cryptocurrency nft blockchain game",
            "date": "", "hn_points": 0, "github_stars": 0, "github_forks": 0,
        }
        assert score_article(ai_article) > score_article(crypto_article)


# ─────────────────────────────────────────────
# rank_articles
# ─────────────────────────────────────────────
class TestRankArticles:
    def _make_articles(self, n: int) -> list:
        return [
            {
                "title": f"Article {i}",
                "url": f"https://example.com/{i}",
                "source": "Hacker News",
                "summary_raw": "llm agent inference",
                "date": "",
                "hn_points": i * 10,
                "github_stars": 0,
                "github_forks": 0,
            }
            for i in range(n)
        ]

    def test_returns_top_n(self):
        articles = self._make_articles(100)
        top, stats = rank_articles(articles, top_n=10)
        assert len(top) == 10

    def test_empty_input(self):
        top, stats = rank_articles([])
        assert top == []
        assert stats["total"] == 0

    def test_sorted_descending(self):
        articles = self._make_articles(20)
        top, _ = rank_articles(articles, top_n=20)
        scores = [a["score"] for a in top]
        assert scores == sorted(scores, reverse=True)

    def test_stats_fields_present(self):
        articles = self._make_articles(5)
        _, stats = rank_articles(articles)
        for field in ("total", "after_ranking", "top_score", "min_score", "avg_score"):
            assert field in stats
