import feedparser
import requests
from config import ARXIV_FEEDS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}

def fetch_arxiv_papers(feed_url: str) -> list[dict]:
    resp = requests.get(feed_url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        items.append({
            "title": getattr(entry, "title", "").replace("\n", " ").strip(),
            "url": getattr(entry, "link", ""),
            "abstract": getattr(entry, "summary", "")[:600],
        })
    return items

def fetch_all_papers() -> list[dict]:
    seen, all_items = set(), []
    for url in ARXIV_FEEDS:
        try:
            for p in fetch_arxiv_papers(url):
                if p["url"] not in seen:
                    seen.add(p["url"])
                    all_items.append(p)
        except Exception as e:
            print(f"[arXiv] {url} 실패: {e}")
    return all_items
