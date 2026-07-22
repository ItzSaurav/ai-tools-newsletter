"""
metrics.py — Generate structured logs and rolling analytics.
(Updated to accept PIPELINE_START/PIPELINE_END from environment.)
"""

from __future__ import annotations

import datetime
import json
import os
import time as _time
from typing import Any

from config import (
    DATA_DIR,
    LOGS_DIR,
    METRICS_FILE,
    ensure_dirs,
    get_logger,
)

log = get_logger(
    "metrics",
    log_file=f"logs/metrics_{datetime.date.today().isoformat()}.log",
)

TODAY_STR = datetime.date.today().isoformat()


def _load_json(path: str, default: Any) -> Any:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def collect_run_data(pipeline_start: float, pipeline_end: float) -> dict:
    fetch_stats = _load_json(f"{DATA_DIR}/fetch_stats.json", {})
    ranking_stats = _load_json(f"{DATA_DIR}/ranking_stats.json", {})
    groq_latency = _load_json(f"{DATA_DIR}/groq_latency.json", {})
    curated = _load_json(f"{DATA_DIR}/curated_items.json", {"curated_items": []})
    n_curated = len(curated.get("curated_items", []))

    draft_path = f"drafts/{TODAY_STR}.html"
    draft_size_kb = round(os.path.getsize(draft_path) / 1024, 1) if os.path.exists(draft_path) else 0

    return {
        "date": TODAY_STR,
        "pipeline_duration_seconds": round(pipeline_end - pipeline_start, 2),
        "fetch": {
            "total_fetched": fetch_stats.get("total_fetched", 0),
            "new_items": fetch_stats.get("new_items", 0),
            "duplicates_removed": fetch_stats.get("duplicates_removed", 0),
            "source_counts": fetch_stats.get("source_counts", {}),
        },
        "ranking": {
            "total_ranked": ranking_stats.get("total", 0),
            "after_ranking": ranking_stats.get("after_ranking", 0),
            "top_score": ranking_stats.get("top_score", 0),
            "avg_score": ranking_stats.get("avg_score", 0),
            "cutoff_score": ranking_stats.get("cutoff_score", 0),
        },
        "curation": {
            "items_in": groq_latency.get("items_in", 0),
            "items_out": n_curated,
            "groq_latency_seconds": groq_latency.get("latency_seconds", 0),
        },
        "draft": {
            "size_kb": draft_size_kb,
        },
    }


def write_daily_log(run_data: dict) -> None:
    ensure_dirs()
    log_path = f"{LOGS_DIR}/{TODAY_STR}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2, ensure_ascii=False)
    log.info(f"Daily log written → {log_path}")


def update_metrics(run_data: dict) -> None:
    metrics = _load_json(METRICS_FILE, {"history": []})
    history: list = metrics.get("history", [])
    history = [h for h in history if h.get("date") != TODAY_STR]
    history.append({
        "date": run_data["date"],
        "total_fetched": run_data["fetch"]["total_fetched"],
        "new_items": run_data["fetch"]["new_items"],
        "curated_count": run_data["curation"]["items_out"],
        "groq_latency_s": run_data["curation"]["groq_latency_seconds"],
        "pipeline_duration_s": run_data["pipeline_duration_seconds"],
        "draft_size_kb": run_data["draft"]["size_kb"],
    })
    history = sorted(history, key=lambda x: x["date"])[-30:]
    total_runs = len(history)
    avg_fetched = round(sum(h["total_fetched"] for h in history) / total_runs, 1) if total_runs else 0
    avg_curated = round(sum(h["curated_count"] for h in history) / total_runs, 1) if total_runs else 0
    avg_groq = round(sum(h["groq_latency_s"] for h in history) / total_runs, 2) if total_runs else 0
    avg_duration = round(sum(h["pipeline_duration_s"] for h in history) / total_runs, 1) if total_runs else 0

    metrics = {
        "last_updated": TODAY_STR,
        "total_runs": total_runs,
        "rolling_30d": {
            "avg_fetched_per_run": avg_fetched,
            "avg_curated_per_run": avg_curated,
            "avg_groq_latency_seconds": avg_groq,
            "avg_pipeline_duration_seconds": avg_duration,
        },
        "history": history,
    }

    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    log.info(f"Metrics updated → {METRICS_FILE} ({total_runs} runs tracked)")


def main() -> None:
    ensure_dirs()

    # Accept timing from environment (set by run_pipeline.py)
    try:
        pipeline_start = float(os.environ.get("PIPELINE_START", 0))
        pipeline_end = float(os.environ.get("PIPELINE_END", 0))
        if pipeline_start == 0:
            pipeline_start = _time.monotonic()
            pipeline_end = _time.monotonic()
    except (ValueError, TypeError):
        pipeline_start = _time.monotonic()
        pipeline_end = _time.monotonic()

    run_data = collect_run_data(pipeline_start, pipeline_end)

    log.info("─── Pipeline Metrics ────────────────────────────")
    log.info(f"  Date            : {run_data['date']}")
    log.info(f"  Total fetched   : {run_data['fetch']['total_fetched']}")
    log.info(f"  New items       : {run_data['fetch']['new_items']}")
    log.info(f"  After ranking   : {run_data['ranking']['after_ranking']}")
    log.info(f"  Curated items   : {run_data['curation']['items_out']}")
    log.info(f"  Groq latency    : {run_data['curation']['groq_latency_seconds']:.2f}s")
    log.info(f"  Draft size      : {run_data['draft']['size_kb']} KB")
    log.info(f"  Total runtime   : {run_data['pipeline_duration_seconds']:.1f}s")
    log.info("─────────────────────────────────────────────────")

    write_daily_log(run_data)
    update_metrics(run_data)


if __name__ == "__main__":
    main()
