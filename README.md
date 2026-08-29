# AI Newsletter Pipeline

An automated data and content pipeline that curates AI ecosystem developments, applies scoring heuristics, runs LLM-assisted curation, and generates publication-ready HTML newsletter drafts on a schedule.

[![Newsletter Pipeline](https://github.com/ItzSaurav/ai-tools-newsletter/actions/workflows/newsletter.yml/badge.svg)](https://github.com/ItzSaurav/ai-tools-newsletter/actions/workflows/newsletter.yml)

## Pipeline Architecture

```
GitHub Actions (Scheduled Cron / Manual Dispatch)
                        |
          +-------------v-------------+
          |      fetch_sources.py     |
          |  Ingests RSS feeds & APIs |
          +-------------+-------------+
                        | raw_items.json
          +-------------v-------------+
          |         ranking.py        |
          |   Heuristic scoring       |
          +-------------+-------------+
                        | ranked_items.json
          +-------------v-------------+
          |       categorize.py       |
          |   Rule-based taxonomy     |
          +-------------+-------------+
                        | categorized_items.json
          +-------------v-------------+
          |         curate.py         |
          |  LLM summarization (Groq) |
          +-------------+-------------+
                        | curated_draft.json
          +-------------v-------------+
          |       build_draft.py      |
          | HTML email template engine|
          +-------------+-------------+
                        | output/draft.html
          +-------------v-------------+
          |    approve_and_send.py    |
          | Email dispatch via SMTP   |
          +---------------------------+
```

## Key Components

- **Source Fetching (`fetch_sources.py`)**: Multi-source scraper ingesting RSS feeds, developer forums, and GitHub trending feeds.
- **Ranking Engine (`ranking.py`)**: Scores items based on recency decay, source authority weights, and keyword relevance.
- **Categorization (`categorize.py`)**: Maps items into defined topics (Developer Tools, LLMs, Research, Infrastructure).
- **Curator (`curate.py`)**: Interfaces with Groq LLM API to extract key technical takeaways and summarize releases.
- **Template Compiler (`build_draft.py`)**: Compiles curated JSON data into a clean, responsive HTML email template.
- **Automated Validation (`validate.py`, `tests/`)**: Unit tests for ranking logic, URL validation, and output schema verification.

## Setup & Local Execution

1. Clone the repository:
   ```bash
   git clone https://github.com/ItzSaurav/ai-tools-newsletter.git
   cd ai-tools-newsletter
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in `.env`:
   ```env
   GROQ_API_KEY=your_key_here
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASS=your_app_password
   ```

4. Run the end-to-end pipeline:
   ```bash
   python run_pipeline.py
   ```

5. Run test suite:
   ```bash
   pytest tests/
   ```

## License

MIT License.
