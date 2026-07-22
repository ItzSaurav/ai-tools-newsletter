import json
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import datetime
from dotenv import load_dotenv
import logging
import urllib.parse
import xml.etree.ElementTree as ET

load_dotenv()

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename=f"logs/fetch_{datetime.datetime.now(datetime.timezone.utc).date().isoformat()}.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

SEEN_ITEMS_FILE = "data/seen_items.json"
RAW_ITEMS_FILE = "data/raw_items.json"

def get_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[ 429, 500, 502, 503, 504 ])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def load_seen_urls():
    if os.path.exists(SEEN_ITEMS_FILE):
        with open(SEEN_ITEMS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def fetch_arxiv(session):
    logging.info("Fetching arXiv...")
    items = []
    try:
        url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI%20OR%20cat:cs.CL%20OR%20cat:cs.CV&sortBy=submittedDate&sortOrder=desc&max_results=30"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text.replace("\n", " ").strip()
            summary = entry.find("atom:summary", ns).text.replace("\n", " ").strip()
            link = entry.find("atom:id", ns).text
            published = entry.find("atom:published", ns).text
            items.append({
                "title": title,
                "url": link,
                "source": "arXiv",
                "summary_raw": summary,
                "date": published
            })
    except Exception as e:
        logging.error(f"Error fetching arXiv: {e}")
    return items

def fetch_hackernews(session):
    logging.info("Fetching Hacker News...")
    items = []
    try:
        url = "http://hn.algolia.com/api/v1/search_by_date?query=AI&tags=story&numericFilters=created_at_i>{}".format(
            int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).timestamp())
        )
        response = session.get(url, timeout=10)
        response.raise_for_status()
        hits = response.json().get("hits", [])[:30]
        for hit in hits:
            # Prefer the actual URL, fallback to HN post
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            items.append({
                "title": hit.get("title", ""),
                "url": link,
                "source": "Hacker News",
                "summary_raw": f"Points: {hit.get('points', 0)} Comments: {hit.get('num_comments', 0)}",
                "date": hit.get("created_at")
            })
    except Exception as e:
        logging.error(f"Error fetching Hacker News: {e}")
    return items

def fetch_github(session):
    logging.info("Fetching GitHub...")
    items = []
    try:
        token = os.getenv("GH_TOKEN")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        
        # Search repositories created in the last 7 days (to have some volume) with AI/Agent topics
        date_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        query = f"topic:ai created:>{date_str}"
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=30"
        
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        repos = response.json().get("items", [])
        for repo in repos:
            items.append({
                "title": repo.get("full_name"),
                "url": repo.get("html_url"),
                "source": "GitHub",
                "summary_raw": repo.get("description") or "No description",
                "date": repo.get("created_at")
            })
    except Exception as e:
        logging.error(f"Error fetching GitHub: {e}")
    return items

def fetch_reddit(session):
    logging.info("Fetching Reddit...")
    items = []
    headers = {"User-Agent": "AIToolsNewsletter/1.0"}
    subreddits = ["MachineLearning", "LocalLLaMA"]
    try:
        for sub in subreddits:
            url = f"https://old.reddit.com/r/{sub}/top.json?t=day&limit=15"
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            posts = response.json().get("data", {}).get("children", [])
            for post in posts:
                data = post["data"]
                # Avoid stickied posts
                if data.get("stickied"):
                    continue
                url_link = data.get("url")
                # If it's a self post or reddit video, use the permalink
                if not url_link or url_link.startswith("https://v.redd.it") or "reddit.com" in url_link:
                    url_link = f"https://old.reddit.com{data.get('permalink')}"
                
                items.append({
                    "title": data.get("title"),
                    "url": url_link,
                    "source": f"Reddit (r/{sub})",
                    "summary_raw": f"Score: {data.get('score', 0)}",
                    "date": datetime.datetime.fromtimestamp(data.get("created_utc", 0)).isoformat()
                })
    except Exception as e:
        logging.error(f"Error fetching Reddit: {e}")
    return items

def main():
    session = get_session()
    seen_urls = load_seen_urls()
    
    arxiv_items = fetch_arxiv(session)
    hn_items = fetch_hackernews(session)
    github_items = fetch_github(session)
    reddit_items = fetch_reddit(session)
    
    all_items = []
    all_items.extend(arxiv_items)
    all_items.extend(hn_items)
    all_items.extend(github_items)
    all_items.extend(reddit_items)
    
    new_items = []
    new_urls = set()
    for item in all_items:
        if item["url"] not in seen_urls and item["url"] not in new_urls:
            new_items.append(item)
            new_urls.add(item["url"])
            seen_urls.add(item["url"])
            
    logging.info(f"Arxiv: {len(arxiv_items)}")
    logging.info(f"Hacker News: {len(hn_items)}")
    logging.info(f"GitHub: {len(github_items)}")
    logging.info(f"Reddit: {len(reddit_items)}")
    logging.info(f"Duplicates removed: {len(all_items) - len(new_items)}")
    logging.info(f"Total new items to process: {len(new_items)}")
    
    os.makedirs("data", exist_ok=True)
    with open(RAW_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_items, f, indent=2)

if __name__ == "__main__":
    main()
