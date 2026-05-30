import feedparser
from datetime import datetime, timezone, timedelta, time
from config import RSS_SOURCES, MAX_BLOG_ITEMS

KST = timezone(timedelta(hours=9))

def _get_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def _today_cutoff() -> datetime:
    now_kst = datetime.now(KST)
    return now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS, **kwargs) -> list[dict]:
    feed = feedparser.parse(url)
    items = []
    cutoff = _today_cutoff()
    for entry in feed.entries:
        pub = _get_date(entry)
        if pub is None or pub < cutoff:
            continue
        summary = getattr(entry, "summary", "") or ""
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "source": name,
            "summary": summary[:500],
            "category": kwargs.get("category", "dev"),
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_blogs() -> list[dict]:
    all_items = []
    for source in RSS_SOURCES:
        try:
            all_items.extend(fetch_rss_entries(
                source["name"], source["url"], category=source.get("category", "dev")
            ))
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
    return all_items
