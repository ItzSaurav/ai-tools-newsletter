"""
ranking.py — Score and rank raw articles before sending to Groq.

Reduces token usage by keeping only the top N most relevant articles.
Each article is scored on weighted signals:
  - Source trustworthiness weight
  - HN points
  - GitHub stars / forks
  - Article recency (age decay)
  - AI keyword density in title + summary
  - Reject keyword penalty
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
from typing import List, Tuple

from config import (
    HIGH_VALUE_KEYWORDS,
    MAX_RANKED_ITEMS,
    RANKED_ITEMS_FILE,
    RAW_ITEMS_FILE,
    REJECT_KEYWORDS,
    SOURCE_WEIGHTS,
    ensure_dirs,
    get_logger,
)

log = get_logger(
    "ranking",
    log_file=f"logs/ranking_{datetime.date.today().isoformat()}.log",
)

TODAY_UTC = datetime.datetime.now(datetime.timezone.utc)


# ─────────────────────────────────────────────
# INDIVIDUAL SIGNALS
# ─────────────────────────────────────────────

def _source_score(source: str) -> float:
    """Return 0–10 based on source trustworthiness."""
    for key, weight in SOURCE_WEIGHTS.items():
        if key.lower() in source.lower():
            return float(weight)
    return 5.0  # default for unknown sources


def _hn_score(hn_points: int) -> float:
    """Log-scaled HN points, max contribution ~10."""
    if hn_points <= 0:
        return 0.0
    return min(10.0, math.log1p(hn_points) * 1.5)


def _github_score(stars: int, forks: int) -> float:
    """Log-scaled GitHub stars + forks, max contribution ~10."""
    combined = stars + forks * 0.5
    if combined <= 0:
        return 0.0
    return min(10.0, math.log1p(combined) * 1.2)


def _recency_score(date_str: str) -> float:
    """
    Recency score (0–10).
    - < 1 day old   → 10
    - < 2 days old  → 8
    - < 7 days old  → 5
    - < 30 days old → 2
    - older / unknown → 0
    """
    if not date_str:
        return 3.0  # unknown → neutral
    try:
        # Handle both ISO format and RFC-2822 (RSS)
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ):
            try:
                dt = datetime.datetime.strptime(date_str[:len(fmt) + 2], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                break
            except ValueError:
                continue
        else:
            return 3.0

        age_hours = (TODAY_UTC - dt).total_seconds() / 3600
        if age_hours < 24:
            return 10.0
        elif age_hours < 48:
            return 8.0
        elif age_hours < 168:  # 7 days
            return 5.0
        elif age_hours < 720:  # 30 days
            return 2.0
        else:
            return 0.0
    except Exception:
        return 3.0


def _keyword_score(title: str, summary: str) -> float:
    """
    AI keyword density score (0–10).
    Count high-value keyword hits in title (weight 3x) and summary (weight 1x).
    """
    text = f"{title} {title} {title} {summary}".lower()
    hits = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text)
    return min(10.0, hits * 1.5)


def _reject_penalty(title: str, summary: str) -> float:
    """
    Return a negative penalty if reject keywords are present.
    """
    text = f"{title} {summary}".lower()
    hits = sum(1 for kw in REJECT_KEYWORDS if kw in text)
    return float(hits * -5)


# ─────────────────────────────────────────────
# COMPOSITE SCORE
# ─────────────────────────────────────────────

# Weights for each signal component (must sum to 1.0)
_WEIGHTS = {
    "source":   0.25,
    "keyword":  0.30,
    "recency":  0.20,
    "hn":       0.10,
    "github":   0.10,
    "penalty":  0.05,
}


def score_article(article: dict) -> float:
    """Compute composite score (0–100) for a single article."""
    s_source  = _source_score(article.get("source", ""))
    s_keyword = _keyword_score(
        article.get("title", ""),
        article.get("summary_raw", ""),
    )
    s_recency = _recency_score(article.get("date", ""))
    s_hn      = _hn_score(article.get("hn_points", 0))
    s_github  = _github_score(
        article.get("github_stars", 0),
        article.get("github_forks", 0),
    )
    penalty   = _reject_penalty(
        article.get("title", ""),
        article.get("summary_raw", ""),
    )

    raw = (
        s_source  * _WEIGHTS["source"]  * 10 +
        s_keyword * _WEIGHTS["keyword"] * 10 +
        s_recency * _WEIGHTS["recency"] * 10 +
        s_hn      * _WEIGHTS["hn"]      * 10 +
        s_github  * _WEIGHTS["github"]  * 10 +
        penalty   * _WEIGHTS["penalty"] * 10
    )
    return max(0.0, min(100.0, round(raw, 2)))


def rank_articles(articles: List[dict], top_n: int = MAX_RANKED_ITEMS) -> Tuple[List[dict], dict]:
    """
    Score all articles, sort descending, return top_n.
    Also returns a stats dict for logging.
    """
    if not articles:
        return [], {"total": 0, "after_ranking": 0, "top_score": 0, "min_score": 0, "avg_score": 0}

    for article in articles:
        article["score"] = score_article(article)

    ranked = sorted(articles, key=lambda x: x["score"], reverse=True)
    top = ranked[:top_n]

    scores = [a["score"] for a in ranked]
    stats = {
        "total": len(ranked),
        "after_ranking": len(top),
        "top_score": scores[0] if scores else 0,
        "min_score": scores[-1] if scores else 0,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "cutoff_score": top[-1]["score"] if top else 0,
    }
    return top, stats


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main() -> None:
    ensure_dirs()

    if not os.path.exists(RAW_ITEMS_FILE):
        log.warning(f"{RAW_ITEMS_FILE} not found. Nothing to rank.")
        return

    with open(RAW_ITEMS_FILE, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    if not raw_items:
        log.info("No items to rank.")
        with open(RANKED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    top_items, stats = rank_articles(raw_items)

    log.info("─── Ranking Summary ─────────────────────────────")
    log.info(f"  Total articles  : {stats['total']}")
    log.info(f"  After ranking   : {stats['after_ranking']}")
    log.info(f"  Top score       : {stats['top_score']}")
    log.info(f"  Avg score       : {stats['avg_score']}")
    log.info(f"  Cutoff score    : {stats['cutoff_score']}")
    log.info("─────────────────────────────────────────────────")

    if top_items:
        log.info("Top 5 articles by score:")
        for i, art in enumerate(top_items[:5], 1):
            log.info(f"  {i}. [{art['score']:.1f}] {art['title'][:70]}…")

    with open(RANKED_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(top_items, f, indent=2, ensure_ascii=False)

    # Save ranking stats for metrics.py
    stats_path = "data/ranking_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    log.info(f"Ranked items saved to {RANKED_ITEMS_FILE}")


if __name__ == "__main__":
    main()
