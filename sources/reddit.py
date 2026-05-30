import feedparser
from datetime import datetime, timezone, timedelta, time
from config import REDDIT_SUBREDDITS, MAX_REDDIT_ITEMS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}
KST = timezone(timedelta(hours=9))

def _today_cutoff() -> datetime:
    now_kst = datetime.now(KST)
    return now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_subreddit(name: str, max_items: int = MAX_REDDIT_ITEMS) -> list[dict]:
    url = f"https://www.reddit.com/r/{name}/top.rss?t=day"
    feed = feedparser.parse(url, request_headers=_HEADERS)
    cutoff = _today_cutoff()
    items = []
    for entry in feed.entries:
        pub = getattr(entry, "published_parsed", None)
        if pub:
            try:
                if datetime(*pub[:6], tzinfo=timezone.utc) < cutoff:
                    continue
            except Exception:
                pass
        title = getattr(entry, "title", "")
        url = getattr(entry, "link", "")
        items.append({
            "title": title,
            "url": url,
            "source": f"r/{name}",
            "summary": "",
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_reddit() -> list[dict]:
    all_items = []
    for name in REDDIT_SUBREDDITS:
        try:
            all_items.extend(fetch_subreddit(name))
        except Exception as e:
            print(f"[Reddit] r/{name} 실패: {e}")
    return all_items
