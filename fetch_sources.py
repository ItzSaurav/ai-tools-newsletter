"""
fetch_sources.py — Fetch from 14 sources, each fully isolated.

Sources:
  1. arXiv API (cs.AI, cs.CL, cs.LG, cs.CV)
  2. Hacker News (Algolia API)
  3. GitHub Search (repo search, AI topics)
  4. GitHub Trending (HTML scrape)
  5. Hugging Face Papers (daily API)
  6. Hugging Face Blog (RSS)
  7. Papers With Code (latest papers API)
  8. OpenAI Blog (RSS)
  9. Anthropic Blog (RSS)
  10. DeepMind Blog (RSS)
  11. Simon Willison Blog (RSS)
  12. Latent Space (RSS)
  13. Dev.to AI tag (RSS)
  14. Reddit — optional, 403 is expected from CI/CD (not a failure)
"""

from __future__ import annotations

import datetime
import json
import os
import time
import urllib.parse
from typing import List, Optional

import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from config import (
    ARXIV_MAX_RESULTS,
    GITHUB_DAYS_BACK,
    GITHUB_MAX_REPOS,
    HF_PAPERS_MAX,
    HN_MAX_HITS,
    PWC_MAX,
    REDDIT_LIMIT_PER_SUB,
    RSS_MAX_ITEMS,
    RAW_ITEMS_FILE,
    SEEN_ITEMS_FILE,
    RawArticle,
    ensure_dirs,
    get_logger,
    get_session,
)

load_dotenv()

log = get_logger(
    "fetch",
    log_file=f"logs/fetch_{datetime.date.today().isoformat()}.log",
)

TODAY_UTC = datetime.datetime.now(datetime.timezone.utc)


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
def load_seen_urls() -> set[str]:
    if os.path.exists(SEEN_ITEMS_FILE):
        with open(SEEN_ITEMS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────
def _make_item(
    title: str,
    url: str,
    source: str,
    summary_raw: str = "",
    date: str = "",
    hn_points: int = 0,
    github_stars: int = 0,
    github_forks: int = 0,
) -> dict:
    return RawArticle(
        title=title.strip(),
        url=url.strip(),
        source=source,
        summary_raw=summary_raw.strip()[:800],  # cap length
        date=date,
        hn_points=hn_points,
        github_stars=github_stars,
        github_forks=github_forks,
    ).to_dict()


def _parse_rss(feed_url: str, source_name: str, session, limit: int = RSS_MAX_ITEMS) -> List[dict]:
    """Generic RSS/Atom feed parser using feedparser."""
    items = []
    try:
        resp = session.get(feed_url, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "")
            url = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if title and url:
                items.append(_make_item(title, url, source_name, summary, published))
    except Exception as exc:
        log.warning(f"RSS fetch failed for {source_name} ({feed_url}): {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 1 — arXiv
# ─────────────────────────────────────────────
def fetch_arxiv(session) -> List[dict]:
    log.info("Fetching arXiv…")
    items = []
    try:
        # feedparser handles the Atom namespace cleanly — no manual %20 encoding needed
        query = "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV"
        params = urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": ARXIV_MAX_RESULTS,
        })
        url = f"https://export.arxiv.org/api/query?{params}"
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            title = entry.get("title", "").replace("\n", " ").strip()
            arxiv_url = entry.get("id", "").replace("http://", "https://")
            summary = entry.get("summary", "").replace("\n", " ").strip()
            published = entry.get("published", "")
            if title and arxiv_url:
                items.append(_make_item(title, arxiv_url, "arXiv", summary, published))
        log.info(f"arXiv: {len(items)} items")
    except Exception as exc:
        log.error(f"arXiv fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 2 — Hacker News (Algolia)
# ─────────────────────────────────────────────
def fetch_hackernews(session) -> List[dict]:
    log.info("Fetching Hacker News…")
    items = []
    try:
        cutoff = int((TODAY_UTC - datetime.timedelta(days=2)).timestamp())
        url = (
            f"https://hn.algolia.com/api/v1/search_by_date"
            f"?query=AI&tags=story&numericFilters=created_at_i%3E{cutoff}"
            f"&hitsPerPage={HN_MAX_HITS}"
        )
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])[:HN_MAX_HITS]
        for hit in hits:
            title = hit.get("title", "")
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            points = hit.get("points") or 0
            comments = hit.get("num_comments") or 0
            items.append(_make_item(
                title, link, "Hacker News",
                summary_raw=f"Points: {points} | Comments: {comments}",
                date=hit.get("created_at", ""),
                hn_points=points,
            ))
        log.info(f"Hacker News: {len(items)} items")
    except Exception as exc:
        log.error(f"Hacker News fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 3 — GitHub Search (new AI repos)
# ─────────────────────────────────────────────
def fetch_github_search(session) -> List[dict]:
    log.info("Fetching GitHub Search…")
    items = []
    try:
        token = os.getenv("GH_TOKEN")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"

        date_str = (TODAY_UTC - datetime.timedelta(days=GITHUB_DAYS_BACK)).strftime("%Y-%m-%d")
        query = f"topic:ai created:>{date_str}"
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={GITHUB_MAX_REPOS}"
        )
        resp = session.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        for repo in resp.json().get("items", []):
            description = repo.get("description") or "No description"
            items.append(_make_item(
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                source="GitHub",
                summary_raw=f"{description} | ⭐ {repo.get('stargazers_count', 0)} | 🍴 {repo.get('forks_count', 0)}",
                date=repo.get("created_at", ""),
                github_stars=repo.get("stargazers_count", 0),
                github_forks=repo.get("forks_count", 0),
            ))
        log.info(f"GitHub Search: {len(items)} items")
    except Exception as exc:
        log.error(f"GitHub Search fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 4 — GitHub Trending (HTML scrape)
# ─────────────────────────────────────────────
def fetch_github_trending(session) -> List[dict]:
    log.info("Fetching GitHub Trending…")
    items = []
    try:
        url = "https://github.com/trending?since=daily&spoken_language_code=en"
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for article in soup.select("article.Box-row")[:20]:
            a_tag = article.select_one("h2 a")
            if not a_tag:
                continue
            repo_path = a_tag.get("href", "").strip("/")
            if not repo_path:
                continue
            repo_url = f"https://github.com/{repo_path}"
            title = repo_path.replace("/", " / ")
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""
            stars_el = article.select_one("a[href$='/stargazers']")
            stars_text = stars_el.get_text(strip=True).replace(",", "") if stars_el else "0"
            try:
                stars = int(stars_text)
            except ValueError:
                stars = 0
            items.append(_make_item(
                title=title,
                url=repo_url,
                source="GitHub Trending",
                summary_raw=f"{description} | ⭐ {stars}",
                github_stars=stars,
            ))
        log.info(f"GitHub Trending: {len(items)} items")
    except Exception as exc:
        log.warning(f"GitHub Trending fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 5 — Hugging Face Papers (daily)
# ─────────────────────────────────────────────
def fetch_huggingface_papers(session) -> List[dict]:
    log.info("Fetching Hugging Face Papers…")
    items = []
    try:
        date_str = TODAY_UTC.strftime("%Y-%m-%d")
        url = f"https://huggingface.co/api/daily_papers?date={date_str}"
        resp = session.get(url, timeout=15)
        if resp.status_code == 404:
            # No papers for today yet — try yesterday
            yesterday = (TODAY_UTC - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            url = f"https://huggingface.co/api/daily_papers?date={yesterday}"
            resp = session.get(url, timeout=15)
        resp.raise_for_status()
        papers = resp.json()
        if isinstance(papers, dict):
            papers = papers.get("papers", [])
        for paper in papers[:HF_PAPERS_MAX]:
            paper_id = paper.get("paper", {}).get("id", "")
            title = paper.get("paper", {}).get("title", "")
            abstract = paper.get("paper", {}).get("abstract", "")
            if not title or not paper_id:
                continue
            arxiv_url = f"https://arxiv.org/abs/{paper_id}"
            items.append(_make_item(title, arxiv_url, "Hugging Face Papers", abstract))
        log.info(f"Hugging Face Papers: {len(items)} items")
    except Exception as exc:
        log.warning(f"Hugging Face Papers fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 6 — Hugging Face Blog (RSS)
# ─────────────────────────────────────────────
def fetch_huggingface_blog(session) -> List[dict]:
    log.info("Fetching Hugging Face Blog…")
    items = _parse_rss(
        "https://huggingface.co/blog/feed.xml",
        "Hugging Face Blog",
        session,
    )
    log.info(f"Hugging Face Blog: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 7 — Papers With Code (latest)
# ─────────────────────────────────────────────
def fetch_paperswithcode(session) -> List[dict]:
    log.info("Fetching Papers With Code…")
    # Use RSS feed — more reliable from CI than JSON API
    items = _parse_rss(
        "https://paperswithcode.com/rss",
        "Papers With Code",
        session,
        limit=PWC_MAX,
    )
    log.info(f"Papers With Code: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 8 — OpenAI Blog (RSS)
# ─────────────────────────────────────────────
def fetch_openai_blog(session) -> List[dict]:
    log.info("Fetching OpenAI Blog…")
    items = _parse_rss(
        "https://openai.com/news/rss.xml",
        "OpenAI Blog",
        session,
    )
    log.info(f"OpenAI Blog: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 9 — Anthropic Blog (HTML scrape)
# ─────────────────────────────────────────────
def fetch_anthropic_blog(session) -> List[dict]:
    log.info("Fetching Anthropic Blog…")
    items = []
    try:
        url = "https://www.anthropic.com/news"
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        seen_hrefs: set[str] = set()
        # Anthropic news page: article links look like /news/<slug>
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Only keep paths that look like individual news articles (not the index)
            if not href.startswith("/news/") or href == "/news/":
                continue
            full_url = f"https://www.anthropic.com{href}"
            if full_url in seen_hrefs:
                continue
            seen_hrefs.add(full_url)

            # Title: prefer explicit heading inside the link, fall back to link text
            heading = a_tag.find(["h2", "h3", "h4"])
            title = heading.get_text(strip=True) if heading else a_tag.get_text(strip=True)
            title = " ".join(title.split())  # collapse whitespace
            if not title or len(title) < 6:
                continue

            # Date: look for a <time> element nearby (parent card)
            date_str = ""
            parent = a_tag.parent
            for _ in range(5):  # walk up max 5 levels
                if parent is None:
                    break
                time_el = parent.find("time")
                if time_el:
                    date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
                    break
                parent = parent.parent

            items.append(_make_item(title, full_url, "Anthropic Blog", date=date_str))
            if len(items) >= RSS_MAX_ITEMS:
                break

        if not items:
            log.warning(
                "Anthropic Blog: 0 items parsed from https://www.anthropic.com/news —"
                " page structure may have changed (selector review needed)"
            )
        else:
            log.info(f"Anthropic Blog: {len(items)} items")
    except Exception as exc:
        log.warning(f"Anthropic Blog fetch failed: {exc}")
    return items


# ─────────────────────────────────────────────
# SOURCE 10 — DeepMind Blog (RSS)
# ─────────────────────────────────────────────
def fetch_deepmind_blog(session) -> List[dict]:
    log.info("Fetching DeepMind Blog…")
    items = _parse_rss(
        "https://deepmind.google/blog/rss.xml",
        "DeepMind Blog",
        session,
    )
    log.info(f"DeepMind Blog: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 11 — Simon Willison Blog (RSS)
# ─────────────────────────────────────────────
def fetch_simon_willison(session) -> List[dict]:
    log.info("Fetching Simon Willison…")
    items = _parse_rss(
        "https://simonwillison.net/atom/everything/",
        "Simon Willison",
        session,
    )
    log.info(f"Simon Willison: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 12 — Latent Space (RSS)
# ─────────────────────────────────────────────
def fetch_latentspace(session) -> List[dict]:
    log.info("Fetching Latent Space…")
    items = _parse_rss(
        "https://www.latent.space/feed",
        "Latent Space",
        session,
    )
    log.info(f"Latent Space: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 13 — Dev.to AI tag (RSS)
# ─────────────────────────────────────────────
def fetch_devto(session) -> List[dict]:
    log.info("Fetching Dev.to AI tag…")
    items = _parse_rss(
        "https://dev.to/feed/tag/ai",
        "Dev.to",
        session,
    )
    log.info(f"Dev.to: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# SOURCE 14 — Reddit (OAuth — free, no credit card)
# ─────────────────────────────────────────────
def _get_reddit_token(session) -> Optional[str]:
    """Get a Reddit OAuth bearer token using client_credentials flow."""
    import requests as _requests_module  # for HTTPBasicAuth
    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        log.warning(
            "Reddit: REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set — skipping"
        )
        return None
    try:
        auth = _requests_module.auth.HTTPBasicAuth(client_id, client_secret)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": "ai-tools-newsletter/2.0 by ItzSaurav"}
        resp = session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token", "")
        if not token:
            log.warning("Reddit OAuth: response had no access_token field")
            return None
        return token
    except Exception as exc:
        log.warning(f"Reddit OAuth token fetch failed: {exc}")
        return None


def fetch_reddit(session) -> List[dict]:
    log.info("Fetching Reddit (OAuth)…")
    token = _get_reddit_token(session)
    if not token:
        log.info("Reddit: 0 items (OAuth credentials unavailable)")
        return []

    items = []
    subreddits = ["MachineLearning", "LocalLLaMA"]
    headers = {
        "Authorization": f"bearer {token}",
        "User-Agent": "ai-tools-newsletter/2.0 by ItzSaurav",
    }
    for sub in subreddits:
        try:
            url = (
                f"https://oauth.reddit.com/r/{sub}/top"
                f"?t=day&limit={REDDIT_LIMIT_PER_SUB}"
            )
            resp = session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                data = post.get("data", {})
                if data.get("stickied"):
                    continue
                link = data.get("url", "")
                if not link or "v.redd.it" in link or "reddit.com" in link:
                    link = f"https://www.reddit.com{data.get('permalink', '')}"
                score = data.get("score", 0)
                items.append(_make_item(
                    title=data.get("title", ""),
                    url=link,
                    source=f"Reddit (r/{sub})",
                    summary_raw=f"Score: {score}",
                    date=datetime.datetime.fromtimestamp(
                        data.get("created_utc", 0), tz=datetime.timezone.utc
                    ).isoformat(),
                ))
            log.info(f"Reddit r/{sub}: {sum(1 for p in posts if not p['data'].get('stickied'))} items")
        except Exception as exc:
            log.warning(f"Reddit r/{sub} fetch failed: {exc}")
    log.info(f"Reddit: {len(items)} items")
    return items


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    ensure_dirs()
    session = get_session()
    seen_urls = load_seen_urls()

    # Execute all fetchers — each is fully isolated
    source_fns = [
        fetch_arxiv,
        fetch_hackernews,
        fetch_github_search,
        fetch_github_trending,
        fetch_huggingface_papers,
        fetch_huggingface_blog,
        fetch_paperswithcode,
        fetch_openai_blog,
        fetch_anthropic_blog,
        fetch_deepmind_blog,
        fetch_simon_willison,
        fetch_latentspace,
        fetch_devto,
        fetch_reddit,
    ]

    source_counts: dict[str, int] = {}
    all_items: List[dict] = []

    for fn in source_fns:
        try:
            fetched = fn(session)
        except Exception as exc:
            log.error(f"Unhandled exception in {fn.__name__}: {exc}")
            fetched = []
        source_counts[fn.__name__] = len(fetched)
        all_items.extend(fetched)

    # Deduplicate by URL (preserve insertion order)
    new_items: List[dict] = []
    seen_in_run: set[str] = set()
    duplicates_removed = 0
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen_urls and url not in seen_in_run:
            new_items.append(item)
            seen_in_run.add(url)
        else:
            duplicates_removed += 1

    # Summary log
    log.info("─── Fetch Summary ───────────────────────────────")
    for fn_name, count in source_counts.items():
        log.info(f"  {fn_name}: {count} items")
    log.info(f"  Total fetched   : {len(all_items)}")
    log.info(f"  Duplicates removed: {duplicates_removed}")
    log.info(f"  New items       : {len(new_items)}")
    log.info("─────────────────────────────────────────────────")

    # Save raw items
    with open(RAW_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_items, f, indent=2, ensure_ascii=False)

    # Save fetch stats for metrics.py
    stats = {
        "date": TODAY_UTC.date().isoformat(),
        "source_counts": source_counts,
        "total_fetched": len(all_items),
        "duplicates_removed": duplicates_removed,
        "new_items": len(new_items),
    }
    import json as _json
    stats_path = f"{os.path.dirname(RAW_ITEMS_FILE)}/fetch_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        _json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
