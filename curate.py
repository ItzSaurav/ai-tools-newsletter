"""
curate.py — Groq-powered curation with a premium editorial prompt.

Uses llama-3.3-70b-versatile to select and enrich the top 8–12 articles
from the pre-ranked, pre-categorized pool.

Output schema per article:
  title, url, source, category, summary (2-3 sentences),
  why_builders_care, difficulty (Beginner/Intermediate/Advanced),
  reading_time_mins, tags (list), confidence_score (0-100)
"""

from __future__ import annotations

import datetime
import json
import os
import time
from typing import Optional

from groq import Groq
from dotenv import load_dotenv

from config import (
    CURATED_ITEMS_FILE,
    GROQ_MAX_RETRIES,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    RANKED_ITEMS_FILE,
    ensure_dirs,
    get_logger,
    CurationError,
)

load_dotenv()

log = get_logger(
    "curate",
    log_file=f"logs/curate_{datetime.date.today().isoformat()}.log",
)

# ─────────────────────────────────────────────
# EDITORIAL SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are the editor-in-chief of "The Builder's Brief" — a premium weekly newsletter \
read by 50,000 AI engineers, ML researchers, and technical founders who build \
production AI systems every day.

Your readers are sophisticated. They are NOT interested in:
- Cryptocurrency, NFTs, Web3
- Generic cloud cost optimization with no AI angle
- Sports, gaming, entertainment, politics
- Non-AI programming tutorials (e.g., "CSS tips", "SQL basics")
- Hype articles with no technical substance
- Startup funding news unless directly AI-product-relevant
- Generic "AI will change everything" think-pieces

Your readers ARE deeply interested in:
- New open-source LLMs (weights, architecture, benchmarks)
- AI coding assistants and developer tooling (Cursor, Copilot, Devin, SWE-Agent)
- Inference optimization (vLLM, Ollama, TensorRT-LLM, llama.cpp, exllamaV2)
- RAG and vector databases (Chroma, Weaviate, Qdrant, pgvector)
- Agent frameworks and orchestration (LangChain, LangGraph, AutoGen, CrewAI)
- Model Context Protocol (MCP) and tool use
- CUDA, GPU, hardware for AI workloads
- Training techniques (LoRA, QLoRA, RLHF, DPO, GRPO)
- Multimodal models (vision, speech, video)
- AI safety, alignment, interpretability
- Practical tutorials with real code that builders can run today
- ArXiv research papers with immediate engineering implications
- Hugging Face model releases and papers
- Industry benchmarks and leaderboards (MMLU, SWE-Bench, LMSYS, LiveBench)
- Open-source releases from Anthropic, OpenAI, Google DeepMind, Meta AI, Mistral

════════════════════════════════════════════
TASK
════════════════════════════════════════════
From the provided list of pre-ranked, pre-categorized articles, select the \
TOP 8 to 12 most valuable items for your readers. Prefer diversity across \
categories. Do NOT include more than 3 items from GitHub repositories unless \
they are exceptional releases.

For EACH selected item, provide ALL of the following fields:

1. "title"            — The article/repo title (can clean up formatting)
2. "url"              — The exact URL from the input (do NOT modify it)
3. "source"           — The source name from the input
4. "category"         — One of: "AI Models" | "AI Tools" | "Coding" | "Research" | \
"Agents" | "Infrastructure" | "Open Source" | "Tutorials" | "Benchmarks" | "Industry News"
5. "summary"          — 2-3 sentences. Factual, technical, no fluff. \
What it does, how it works, what makes it notable.
6. "why_builders_care" — 1 punchy sentence. What can a builder DO with this today?
7. "difficulty"       — "Beginner" | "Intermediate" | "Advanced"
8. "reading_time_mins" — Estimated integer minutes to read/skim (1–20)
9. "tags"             — List of 3–6 lowercase tags, e.g. ["llm", "rag", "open-source"]
10. "confidence_score" — Integer 0–100. How confident are you this is valuable to builders?

════════════════════════════════════════════
OUTPUT FORMAT
════════════════════════════════════════════
Return ONLY valid JSON. No markdown fences. No explanation outside the JSON.

{
  "intro": "1-2 sentences setting the tone for this edition — what's the headline theme?",
  "curated_items": [
    {
      "title": "...",
      "url": "...",
      "source": "...",
      "category": "...",
      "summary": "...",
      "why_builders_care": "...",
      "difficulty": "...",
      "reading_time_mins": 5,
      "tags": ["tag1", "tag2"],
      "confidence_score": 85
    }
  ]
}
"""


def _build_user_prompt(items: list) -> str:
    """Format ranked items for the Groq user message."""
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            f"[{i}] SCORE={item.get('score', 0):.1f} | "
            f"SOURCE={item.get('source', '?')} | "
            f"CATEGORY={item.get('preliminary_category', '?')}\n"
            f"TITLE: {item.get('title', '(no title)')}\n"
            f"URL: {item.get('url', '')}\n"
            f"SUMMARY: {item.get('summary_raw', '')[:300]}\n"
        )
    return (
        f"Here are {len(items)} pre-ranked articles for today's edition. "
        f"Select the best 8-12 for The Builder's Brief:\n\n"
        + "\n".join(lines)
    )


def call_groq_with_backoff(client: Groq, prompt: str) -> tuple[str, float]:
    """
    Call Groq with exponential backoff.
    Returns (response_text, latency_seconds).
    """
    delay = 2
    for attempt in range(GROQ_MAX_RETRIES):
        try:
            log.info(f"Groq API call (attempt {attempt + 1}/{GROQ_MAX_RETRIES})…")
            t0 = time.monotonic()
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=GROQ_TEMPERATURE,
                response_format={"type": "json_object"},
                max_tokens=4096,
            )
            latency = time.monotonic() - t0
            log.info(f"Groq responded in {latency:.2f}s")
            return completion.choices[0].message.content, latency
        except Exception as exc:
            log.warning(f"Groq API error (attempt {attempt + 1}): {exc}")
            if attempt < GROQ_MAX_RETRIES - 1:
                log.info(f"Retrying in {delay}s…")
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise CurationError(f"Groq failed after {GROQ_MAX_RETRIES} attempts: {exc}") from exc


def main() -> None:
    ensure_dirs()

    if not os.path.exists(RANKED_ITEMS_FILE):
        log.warning(f"{RANKED_ITEMS_FILE} not found. Falling back to raw items.")
        input_file = "data/raw_items.json"
    else:
        input_file = RANKED_ITEMS_FILE

    if not os.path.exists(input_file):
        log.error("No input file for curation. Aborting.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        log.info("No items to curate.")
        with open(CURATED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump({"intro": "", "curated_items": []}, f, indent=2)
        return

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        log.error("GROQ_API_KEY not set. Aborting curation.")
        return

    client = Groq(api_key=api_key)
    user_prompt = _build_user_prompt(items)

    try:
        response_text, latency = call_groq_with_backoff(client, user_prompt)
        curated_data = json.loads(response_text)

        n_curated = len(curated_data.get("curated_items", []))
        log.info(f"Curated {n_curated} items in {latency:.2f}s")

        # Inject source field if Groq omitted it
        for raw in items:
            raw_url = raw.get("url", "")
            for curated in curated_data.get("curated_items", []):
                if curated.get("url") == raw_url and not curated.get("source"):
                    curated["source"] = raw.get("source", "")

        with open(CURATED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(curated_data, f, indent=2, ensure_ascii=False)

        # Save latency for metrics
        latency_path = "data/groq_latency.json"
        with open(latency_path, "w", encoding="utf-8") as f:
            json.dump({"latency_seconds": round(latency, 3), "items_in": len(items), "items_out": n_curated}, f)

    except json.JSONDecodeError as exc:
        log.error(f"Groq response was not valid JSON: {exc}\nResponse:\n{response_text[:500]}")
    except CurationError as exc:
        log.error(str(exc))
    except Exception as exc:
        log.error(f"Unexpected error in curation: {exc}")


if __name__ == "__main__":
    main()
