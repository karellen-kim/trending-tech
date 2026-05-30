import feedparser
from datetime import datetime, timezone, timedelta
from config import RSS_SOURCES, MAX_BLOG_ITEMS

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS) -> list[dict]:
    feed = feedparser.parse(url)
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    for entry in feed.entries:
        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue
        except Exception:
            pass
        summary = getattr(entry, "summary", "") or ""
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "source": name,
            "summary": summary[:500],
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_blogs() -> list[dict]:
    all_items = []
    for source in RSS_SOURCES:
        try:
            all_items.extend(fetch_rss_entries(source["name"], source["url"]))
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
    return all_items
