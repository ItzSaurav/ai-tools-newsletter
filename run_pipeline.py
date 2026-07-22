"""
run_pipeline.py — Master orchestrator for the newsletter pipeline.

Stages:
  1. fetch_sources.py  — Pull from 14 sources
  2. ranking.py        — Score + filter top 50
  3. categorize.py     — Rule-based pre-categorization
  4. curate.py         — Groq editorial curation
  5. validate.py       — Quality gate (stop if fails)
  6. build_draft.py    — Build premium HTML + send review email
  7. metrics.py        — Write JSON logs and rolling analytics

Run locally:
  python run_pipeline.py

Dry run (no email, no state write):
  DRY_RUN=true python run_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [pipeline] %(levelname)s — %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("pipeline")

PIPELINE_STAGES = [
    "fetch_sources.py",
    "ranking.py",
    "categorize.py",
    "curate.py",
    "validate.py",
    "build_draft.py",
]


def run_stage(script: str, stage_times: dict) -> None:
    log.info(f"▶ Starting {script}…")
    t0 = time.monotonic()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - t0
    stage_times[script] = round(elapsed, 2)

    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            log.debug(f"  [{script}] {line}")
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            # Print stderr directly (it contains our structured logging output)
            print(f"  {line}", file=sys.stderr)

    if result.returncode != 0:
        log.error(f"✗ {script} failed (exit {result.returncode}) after {elapsed:.1f}s")
        sys.exit(result.returncode)

    log.info(f"✓ {script} completed in {elapsed:.1f}s")


def run_metrics(pipeline_start: float, pipeline_end: float) -> None:
    """Run metrics.py with timing data via environment."""
    import os
    env = os.environ.copy()
    env["PIPELINE_START"] = str(pipeline_start)
    env["PIPELINE_END"] = str(pipeline_end)
    result = subprocess.run(
        [sys.executable, "metrics.py"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            print(f"  {line}", file=sys.stderr)
    if result.returncode != 0:
        log.warning(f"metrics.py exited with {result.returncode} — non-fatal")


def main() -> None:
    log.info("══════════════════════════════════════════════")
    log.info("  The Builder's Brief — Newsletter Pipeline  ")
    log.info("══════════════════════════════════════════════")

    pipeline_start = time.monotonic()
    stage_times: dict[str, float] = {}

    for stage in PIPELINE_STAGES:
        run_stage(stage, stage_times)

    pipeline_end = time.monotonic()
    total = pipeline_end - pipeline_start

    # Always run metrics last (non-fatal)
    run_metrics(pipeline_start, pipeline_end)

    log.info("══════════════════════════════════════════════")
    log.info(f"  Pipeline complete in {total:.1f}s")
    for stage, t in stage_times.items():
        log.info(f"    {stage:<25} {t:.1f}s")
    log.info("══════════════════════════════════════════════")


if __name__ == "__main__":
    main()
