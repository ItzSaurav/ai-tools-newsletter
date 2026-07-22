"""
config.py — Central configuration, constants, shared utilities.
All pipeline scripts import from here for consistency.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────
# FILE PATHS
# ─────────────────────────────────────────────
DATA_DIR = "data"
LOGS_DIR = "logs"
DRAFTS_DIR = "drafts"
TESTS_DIR = "tests"

SEEN_ITEMS_FILE = f"{DATA_DIR}/seen_items.json"
RAW_ITEMS_FILE = f"{DATA_DIR}/raw_items.json"
RANKED_ITEMS_FILE = f"{DATA_DIR}/ranked_items.json"
CURATED_ITEMS_FILE = f"{DATA_DIR}/curated_items.json"
METRICS_FILE = f"{DATA_DIR}/metrics.json"
PIPELINE_STATE_FILE = f"{DATA_DIR}/pipeline_state.json"

# ─────────────────────────────────────────────
# PIPELINE SETTINGS
# ─────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_TEMPERATURE = 0.3
GROQ_MAX_RETRIES = 5

MAX_RANKED_ITEMS = 50        # Items sent to Groq after ranking
MAX_RAW_ITEMS_FALLBACK = 150 # Fallback cap if ranking not run

# Source fetch limits
ARXIV_MAX_RESULTS = 30
HN_MAX_HITS = 30
GITHUB_MAX_REPOS = 30
GITHUB_DAYS_BACK = 7
REDDIT_LIMIT_PER_SUB = 15
HF_PAPERS_MAX = 20
PWC_MAX = 20
RSS_MAX_ITEMS = 20

# ─────────────────────────────────────────────
# SOURCE REGISTRY
# Each entry: (name, weight) for ranking
# ─────────────────────────────────────────────
SOURCE_WEIGHTS = {
    "arXiv": 9,
    "Hacker News": 8,
    "GitHub": 7,
    "Hugging Face Papers": 9,
    "Hugging Face Blog": 8,
    "Papers With Code": 9,
    "OpenAI Blog": 9,
    "Anthropic Blog": 9,
    "DeepMind Blog": 9,
    "Simon Willison": 8,
    "Latent Space": 8,
    "GitHub Trending": 7,
    "Dev.to": 6,
    "Reddit (r/MachineLearning)": 7,
    "Reddit (r/LocalLLaMA)": 7,
}

# ─────────────────────────────────────────────
# AI KEYWORD LISTS (for ranking and categorization)
# ─────────────────────────────────────────────
HIGH_VALUE_KEYWORDS = [
    "llm", "large language model", "gpt", "claude", "gemini", "llama", "mistral",
    "deepseek", "qwen", "phi", "falcon", "mamba", "transformer",
    "agent", "agentic", "multi-agent", "autonomous agent", "rag", "retrieval augmented",
    "vector database", "vector store", "embedding", "semantic search",
    "mcp", "model context protocol", "tool use", "function calling",
    "fine-tuning", "fine tuning", "lora", "qlora", "peft", "rlhf", "dpo",
    "inference", "vllm", "ollama", "tensorrt", "triton", "cuda",
    "langchain", "langgraph", "openai", "anthropic", "hugging face", "huggingface",
    "diffusion", "stable diffusion", "flux", "sora",
    "multimodal", "vision model", "vlm", "speech", "whisper", "tts",
    "benchmark", "evals", "mmlu", "swe-bench", "lmsys",
    "robotics", "embodied ai", "reinforcement learning",
    "context window", "attention", "mixture of experts", "moe",
    "speculative decoding", "quantization", "pruning", "distillation",
    "ai safety", "alignment", "interpretability", "mechanistic",
    "prompt engineering", "system prompt", "few-shot", "chain of thought",
    "code generation", "copilot", "cursor", "devin", "swe-agent",
]

REJECT_KEYWORDS = [
    "cryptocurrency", "bitcoin", "ethereum", "nft", "blockchain game",
    "sports", "football", "basketball", "soccer",
    "celebrity", "entertainment", "movie", "tv show",
    "politics", "election", "president", "congress",
    "cooking", "recipe", "food blog",
    "travel", "tourism",
    "generic cloud", "aws pricing", "azure cost",
    "database migration", "sql tutorial",
]

# ─────────────────────────────────────────────
# CATEGORIES
# ─────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "AI Models": [
        "model", "llm", "gpt", "claude", "gemini", "llama", "mistral", "deepseek",
        "transformer", "architecture", "fine-tun", "pretrain", "checkpoint",
        "weights", "gguf", "ggml", "quantiz",
    ],
    "AI Tools": [
        "tool", "sdk", "api", "library", "framework", "platform", "assistant",
        "copilot", "cursor", "plugin", "extension", "integration",
        "langchain", "langgraph", "llamaindex", "haystack",
    ],
    "Coding": [
        "code gen", "code generation", "coding", "programmer", "devin", "swe",
        "github copilot", "codebase", "debugging", "refactor", "ide",
    ],
    "Research": [
        "paper", "arxiv", "research", "study", "survey", "analysis", "benchmark",
        "experiment", "evaluation", "findings", "propose", "novel",
    ],
    "Agents": [
        "agent", "agentic", "multi-agent", "autonomous", "workflow", "orchestrat",
        "tool use", "function calling", "mcp", "planning", "reasoning",
    ],
    "Infrastructure": [
        "inference", "vllm", "ollama", "triton", "cuda", "gpu", "serving",
        "deploy", "scalab", "performance", "latency", "throughput", "tensorrt",
        "quantiz", "pruning", "distillation", "hardware",
    ],
    "Open Source": [
        "open source", "open-source", "github", "release", "mit license",
        "apache", "community", "contribution", "repo", "repository",
    ],
    "Tutorials": [
        "tutorial", "guide", "how to", "walkthrough", "beginner", "introduction",
        "learn", "course", "workshop", "getting started",
    ],
    "Benchmarks": [
        "benchmark", "leaderboard", "mmlu", "swe-bench", "lmsys", "evals",
        "evaluation", "score", "metric", "compare", "ranking",
    ],
    "Industry News": [
        "announce", "launch", "release", "funding", "raised", "billion",
        "partnership", "acquisition", "company", "startup", "series",
    ],
}

# ─────────────────────────────────────────────
# TYPED DATACLASSES
# ─────────────────────────────────────────────
@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    summary_raw: str = ""
    date: str = ""
    score: float = 0.0
    hn_points: int = 0
    github_stars: int = 0
    github_forks: int = 0
    preliminary_category: str = "Industry News"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "summary_raw": self.summary_raw,
            "date": self.date,
            "score": self.score,
            "hn_points": self.hn_points,
            "github_stars": self.github_stars,
            "github_forks": self.github_forks,
            "preliminary_category": self.preliminary_category,
        }


@dataclass
class CuratedItem:
    title: str
    url: str
    source: str
    category: str
    summary: str
    why_builders_care: str
    difficulty: str = "Intermediate"
    reading_time_mins: int = 5
    tags: List[str] = field(default_factory=list)
    confidence_score: int = 75

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "summary": self.summary,
            "why_builders_care": self.why_builders_care,
            "difficulty": self.difficulty,
            "reading_time_mins": self.reading_time_mins,
            "tags": self.tags,
            "confidence_score": self.confidence_score,
        }


# ─────────────────────────────────────────────
# CUSTOM EXCEPTIONS
# ─────────────────────────────────────────────
class NewsletterError(Exception):
    """Base exception for the newsletter pipeline."""


class FetchError(NewsletterError):
    """Raised when a source fetch fails unrecoverably."""


class CurationError(NewsletterError):
    """Raised when Groq curation fails after all retries."""


class ValidationError(NewsletterError):
    """Raised when the quality gate check fails."""


class EmailError(NewsletterError):
    """Raised when email sending fails."""


# ─────────────────────────────────────────────
# SHARED HTTP SESSION FACTORY
# ─────────────────────────────────────────────
def get_session(
    total_retries: int = 5,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (429, 500, 502, 503, 504),
) -> Session:
    """Return a requests Session with retry logic pre-configured."""
    session = Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": (
            "AI-Tools-Newsletter/2.0 "
            "(https://github.com/ItzSaurav/ai-tools-newsletter)"
        )
    })
    return session


# ─────────────────────────────────────────────
# SHARED LOGGER FACTORY
# ─────────────────────────────────────────────
def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """
    Return a named logger.
    - Always logs to stderr (visible in GitHub Actions).
    - Optionally writes to a file as well.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s — %(message)s")

    # Console handler (stderr)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Optional file handler
    if log_file:
        os.makedirs(LOGS_DIR, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def ensure_dirs() -> None:
    """Create required runtime directories if they don't exist."""
    for d in (DATA_DIR, LOGS_DIR, DRAFTS_DIR):
        os.makedirs(d, exist_ok=True)
