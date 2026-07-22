# The Builder's Brief — AI Newsletter Pipeline

> Fully autonomous AI newsletter generator. Curates the best AI tools, research, and agents daily. 100% free stack. Manual approval before send.

[![Newsletter Pipeline](https://github.com/ItzSaurav/ai-tools-newsletter/actions/workflows/newsletter.yml/badge.svg)](https://github.com/ItzSaurav/ai-tools-newsletter/actions/workflows/newsletter.yml)

---

## Architecture

```
GitHub Actions (cron 08:00 UTC / workflow_dispatch)
                        │
         ┌──────────────▼──────────────┐
         │      fetch_sources.py       │
         │  14 sources, each isolated  │
         └──────────────┬──────────────┘
                        │ raw_items.json
         ┌──────────────▼──────────────┐
         │         ranking.py          │
         │  Weighted scoring → top 50  │
         └──────────────┬──────────────┘
                        │ ranked_items.json
         ┌──────────────▼──────────────┐
         │        categorize.py        │
         │  Rule-based pre-labeling    │
         └──────────────┬──────────────┘
                        │ (annotated ranked_items.json)
         ┌──────────────▼──────────────┐
         │          curate.py          │
         │  Groq llama-3.3-70b editor  │
         └──────────────┬──────────────┘
                        │ curated_items.json
         ┌──────────────▼──────────────┐
         │         validate.py         │
         │  Quality gate (stops pipe)  │
         └──────────────┬──────────────┘
                        │ ✅ pass
         ┌──────────────▼──────────────┐
         │        build_draft.py       │
         │  Premium HTML email + send  │
         └──────────────┬──────────────┘
                        │ drafts/YYYY-MM-DD.html
         ┌──────────────▼──────────────┐
         │          metrics.py         │
         │  JSON logs + rolling stats  │
         └──────────────┬──────────────┘
                        │
              📧 Review email → Gmail inbox
                        │
              (Manual approval)
                        │
         ┌──────────────▼──────────────┐
         │      approve_and_send.py    │
         │  Send to all recipients     │
         └─────────────────────────────┘
```

---

## Sources (14 total)

| Source | Type | Notes |
|---|---|---|
| arXiv | API | cs.AI, cs.CL, cs.LG, cs.CV |
| Hacker News | Algolia API | Top AI stories last 48h |
| GitHub Search | REST API | New repos with `topic:ai` |
| GitHub Trending | HTML scrape | Daily trending repos |
| Hugging Face Papers | API | Daily curated papers |
| Hugging Face Blog | RSS | Official HF blog |
| Papers With Code | API | Latest papers with code |
| OpenAI Blog | RSS | Official OpenAI news |
| Anthropic Blog | RSS | Official Anthropic news |
| DeepMind Blog | RSS | Official DeepMind news |
| Simon Willison | RSS | AI engineering insights |
| Latent Space | RSS | AI engineering podcast blog |
| Dev.to | RSS | `#ai` tag posts |
| Reddit | JSON API | r/MachineLearning, r/LocalLLaMA (optional — 403 in CI is expected) |

---

## Folder Structure

```
ai-tools-newsletter/
├── .github/
│   └── workflows/
│       └── newsletter.yml      # GitHub Actions cron pipeline
├── data/
│   ├── seen_items.json         # Deduplication state (committed)
│   ├── raw_items.json          # Fetched items (per run)
│   ├── ranked_items.json       # After scoring/filtering
│   ├── curated_items.json      # Groq output
│   ├── metrics.json            # Rolling 30-day analytics
│   └── fetch_stats.json        # Per-run fetch metadata
├── drafts/
│   ├── YYYY-MM-DD.html         # HTML email draft
│   └── YYYY-MM-DD.json         # Curated items snapshot
├── logs/
│   ├── YYYY-MM-DD.json         # Structured daily run log
│   └── *.log                   # Text logs per script
├── tests/
│   ├── test_ranking.py         # Unit tests for ranking engine
│   └── test_validate.py        # Unit tests for quality gate
│
├── config.py                   # Central config, dataclasses, exceptions
├── fetch_sources.py            # Source fetching (14 sources)
├── ranking.py                  # Weighted scoring + top-N selection
├── categorize.py               # Rule-based pre-categorization
├── curate.py                   # Groq editorial curation
├── validate.py                 # Pre-send quality gate
├── build_draft.py              # HTML email builder + review send
├── metrics.py                  # JSON logs + rolling analytics
├── run_pipeline.py             # Master orchestrator
├── approve_and_send.py         # Manual approval → send to list
│
├── recipients.txt              # One subscriber email per line
├── requirements.txt            # Pinned Python dependencies
├── .env.example                # Local dev secrets template
└── README.md
```

---

## Pipeline Flow (Detailed)

### 1. Fetch (`fetch_sources.py`)
- Runs 14 source fetchers **in isolation** — one failure never blocks others
- Uses `feedparser` for RSS/Atom feeds (ArXiv, HF Blog, OpenAI, Anthropic, etc.)
- Deduplicates by URL against `data/seen_items.json`
- Saves `data/raw_items.json` + `data/fetch_stats.json`

### 2. Rank (`ranking.py`)
- Scores every article 0–100 using 5 weighted signals:
  - **Source trust weight** (arXiv=9, HN=8, GitHub=7, etc.)
  - **HN points** (log-scaled)
  - **GitHub stars/forks** (log-scaled)
  - **Article recency** (decay over 30 days)
  - **AI keyword density** (50+ high-value keywords)
- Apply **reject keyword penalty** (crypto, politics, gaming, etc.)
- Keeps **top 50** for Groq — reducing token usage dramatically

### 3. Categorize (`categorize.py`)
- Assigns a `preliminary_category` using keyword rules
- Categories: AI Models, AI Tools, Coding, Research, Agents, Infrastructure, Open Source, Tutorials, Benchmarks, Industry News
- Groq can override or refine

### 4. Curate (`curate.py`)
- Sends pre-ranked, pre-categorized pool to Groq (`llama-3.3-70b-versatile`)
- Premium editorial prompt: selects 8–12 best items for AI builders
- Output schema: title, url, source, category, summary, why_builders_care, difficulty, reading_time_mins, tags, confidence_score
- Tracks Groq latency → `data/groq_latency.json`

### 5. Validate (`validate.py`)
- Quality gate before email is sent
- Checks: min 3 items, no duplicate titles/URLs, all required fields present, valid difficulty, confidence score 0–100
- **Pipeline stops** if validation fails — no empty newsletter is sent

### 6. Build Draft (`build_draft.py`)
- Generates premium responsive HTML email (inline CSS, Gmail-safe)
- Dark gradient header with edition date and item count
- Per-category colored section headers
- Article cards: title + link, 2-3 sentence summary, "Why builders care", Read button, source badge, difficulty badge, reading time, tags
- Dark footer with repo link
- Emails review draft to `GMAIL_USER` for approval

### 7. Metrics (`metrics.py`)
- Writes `logs/YYYY-MM-DD.json` — full run metadata
- Appends to `data/metrics.json` — rolling 30-day stats

---

## Deployment Guide

### Repository Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `GH_TOKEN` | GitHub Personal Access Token (repo scope) |
| `GROQ_API_KEY` | Groq Cloud API key (free tier available) |
| `GMAIL_USER` | Your Gmail address (sender) |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your account password) |

### Gmail App Password Setup
1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**
3. Create an **App Password** → choose "Mail" + "Windows Computer"
4. Copy the 16-character password → use as `GMAIL_APP_PASSWORD`

### Workflow Permissions
Go to **Settings → Actions → General → Workflow permissions** → select **Read and write permissions**.

---

## Local Development

```bash
# Clone
git clone https://github.com/ItzSaurav/ai-tools-newsletter.git
cd ai-tools-newsletter

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Add recipients
echo "you@example.com" > recipients.txt

# Dry run (no email, no state write)
DRY_RUN=true python run_pipeline.py

# Full run (sends review email to GMAIL_USER)
python run_pipeline.py
```

### Approving and Sending
After receiving the `[REVIEW]` email and it looks good:

```bash
python approve_and_send.py drafts/YYYY-MM-DD.html
```

This will:
1. Send the newsletter to all addresses in `recipients.txt` (via BCC)
2. Update `data/seen_items.json` to prevent re-publishing
3. Commit and push state changes to GitHub

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover:
- Ranking signal functions (source weight, HN score, GitHub score, recency, keyword density)
- Composite scoring and top-N selection
- Validation quality gate (all required fields, duplicates, URL format, difficulty, confidence score)

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `GROQ_API_KEY` error | Verify secret is set in repo settings |
| Email not received | Check spam folder; verify Gmail App Password |
| ArXiv returns 0 items | ArXiv sometimes rate-limits CI IPs — HF Papers and PWC cover the same content |
| Reddit returns 403 | Expected from GitHub Actions IPs — Reddit is optional, pipeline continues |
| `ValidationError` raised | Check `logs/YYYY-MM-DD.json` for which validation check failed |
| Workflow shows yellow ⚠️ | Node.js 20 deprecation warning — cosmetic only, does not affect pipeline |

---

## Analytics

After each run, `data/metrics.json` contains rolling 30-day statistics:

```json
{
  "last_updated": "2026-07-22",
  "total_runs": 1,
  "rolling_30d": {
    "avg_fetched_per_run": 156.0,
    "avg_curated_per_run": 10.0,
    "avg_groq_latency_seconds": 3.45,
    "avg_pipeline_duration_seconds": 28.0
  },
  "history": [...]
}
```

---

*Generated by [AI Tools Newsletter Pipeline](https://github.com/ItzSaurav/ai-tools-newsletter)*