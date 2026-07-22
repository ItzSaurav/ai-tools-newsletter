"""
validate.py — Quality gate before the email draft is built.

Checks:
  - Minimum number of curated items
  - No duplicate titles
  - No duplicate URLs
  - Required fields present (title, url, summary, category, why_builders_care)
  - URLs are non-empty strings starting with http
  - Difficulty is one of the allowed values
  - confidence_score is 0–100

If ANY check fails, raises ValidationError to stop the pipeline.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import List, Set

from config import (
    CURATED_ITEMS_FILE,
    ValidationError,
    ensure_dirs,
    get_logger,
)

log = get_logger(
    "validate",
    log_file=f"logs/validate_{datetime.date.today().isoformat()}.log",
)

REQUIRED_FIELDS = ["title", "url", "summary", "category", "why_builders_care"]
ALLOWED_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}
MIN_ITEMS = 3


def validate_items(items: List[dict]) -> None:
    """
    Run all quality checks on curated items.
    Raises ValidationError with a descriptive message if any check fails.
    """
    errors: List[str] = []

    if len(items) < MIN_ITEMS:
        errors.append(
            f"Too few curated items: {len(items)} (minimum is {MIN_ITEMS}). "
            "Pipeline will not send an empty or near-empty newsletter."
        )

    seen_titles: Set[str] = set()
    seen_urls: Set[str] = set()

    for i, item in enumerate(items, 1):
        prefix = f"Item {i} ('{item.get('title', '<no title>')[:40]}')"

        # Required fields
        for field in REQUIRED_FIELDS:
            val = item.get(field)
            if not val or not str(val).strip():
                errors.append(f"{prefix}: missing required field '{field}'")

        # URL format
        url = item.get("url", "")
        if url and not url.startswith("http"):
            errors.append(f"{prefix}: URL does not start with 'http': {url[:60]}")

        # Duplicate title
        title_key = item.get("title", "").strip().lower()
        if title_key in seen_titles:
            errors.append(f"{prefix}: duplicate title detected")
        else:
            seen_titles.add(title_key)

        # Duplicate URL
        if url in seen_urls:
            errors.append(f"{prefix}: duplicate URL detected: {url[:60]}")
        else:
            if url:
                seen_urls.add(url)

        # Difficulty
        difficulty = item.get("difficulty", "")
        if difficulty and difficulty not in ALLOWED_DIFFICULTIES:
            errors.append(
                f"{prefix}: invalid difficulty '{difficulty}' "
                f"(must be one of {ALLOWED_DIFFICULTIES})"
            )

        # Confidence score
        conf = item.get("confidence_score")
        if conf is not None:
            try:
                conf_int = int(conf)
                if not (0 <= conf_int <= 100):
                    errors.append(f"{prefix}: confidence_score {conf_int} is out of range 0–100")
            except (TypeError, ValueError):
                errors.append(f"{prefix}: confidence_score is not a number: {conf!r}")

    if errors:
        error_summary = "\n  ".join(errors)
        raise ValidationError(
            f"Validation failed with {len(errors)} error(s):\n  {error_summary}"
        )


def main() -> None:
    ensure_dirs()

    if not os.path.exists(CURATED_ITEMS_FILE):
        raise ValidationError(f"{CURATED_ITEMS_FILE} not found. Cannot validate.")

    with open(CURATED_ITEMS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("curated_items", [])
    log.info(f"Validating {len(items)} curated items…")

    try:
        validate_items(items)
        log.info("✅ Validation passed. All quality checks passed.")
    except ValidationError as exc:
        log.error(f"❌ Validation FAILED:\n{exc}")
        raise  # re-raise so run_pipeline.py aborts


if __name__ == "__main__":
    main()
