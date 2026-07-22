"""
categorize.py — Rule-based pre-categorization of articles before Groq.

Assigns a preliminary category to each article using keyword matching.
Groq can override or merge categories during curation.

Categories:
  AI Models | AI Tools | Coding | Research | Agents |
  Infrastructure | Open Source | Tutorials | Benchmarks | Industry News
"""

from __future__ import annotations

import datetime
import json
import os
from typing import List

from config import (
    CATEGORY_KEYWORDS,
    RANKED_ITEMS_FILE,
    ensure_dirs,
    get_logger,
)

log = get_logger(
    "categorize",
    log_file=f"logs/categorize_{datetime.date.today().isoformat()}.log",
)

# Priority order for category assignment (first match wins)
CATEGORY_PRIORITY = [
    "Research",
    "Agents",
    "AI Models",
    "Infrastructure",
    "Benchmarks",
    "AI Tools",
    "Coding",
    "Open Source",
    "Tutorials",
    "Industry News",
]


def assign_category(title: str, summary: str, source: str) -> str:
    """
    Assign a preliminary category based on keyword matching.
    Returns the first matching category in priority order.
    """
    text = f"{title} {summary} {source}".lower()

    for cat in CATEGORY_PRIORITY:
        keywords = CATEGORY_KEYWORDS.get(cat, [])
        if any(kw.lower() in text for kw in keywords):
            return cat

    return "Industry News"  # default


def categorize_items(items: List[dict]) -> List[dict]:
    """Add 'preliminary_category' field to each item in-place."""
    category_counts: dict[str, int] = {}

    for item in items:
        cat = assign_category(
            item.get("title", ""),
            item.get("summary_raw", ""),
            item.get("source", ""),
        )
        item["preliminary_category"] = cat
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return items, category_counts


def main() -> None:
    ensure_dirs()

    if not os.path.exists(RANKED_ITEMS_FILE):
        log.warning(f"{RANKED_ITEMS_FILE} not found. Skipping categorization.")
        return

    with open(RANKED_ITEMS_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        log.info("No items to categorize.")
        return

    items, category_counts = categorize_items(items)

    log.info("─── Categorization Summary ──────────────────────")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        log.info(f"  {cat:<20}: {count}")
    log.info("─────────────────────────────────────────────────")

    # Overwrite ranked items with categorized version
    with open(RANKED_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    log.info(f"Categorization complete. {len(items)} items updated.")


if __name__ == "__main__":
    main()
