from time import sleep

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from config import now_kst
from config import REDDIT_SUBREDDITS, MAX_REDDIT_ITEMS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}
KST = timezone(timedelta(hours=9))
MAX_ATTEMPTS = 3
MAX_RETRY_WAIT = 30


def _utc_now() -> datetime:
    """HTTP 날짜 형태의 Retry-After를 계산할 UTC 시각을 제공한다."""
    return datetime.now(timezone.utc)


def _retry_delay(value: str | None, attempt: int) -> float:
    """유효한 서버 대기를 우선하고 없거나 잘못된 헤더에는 제한된 backoff를 쓴다."""
    if value:
        if value.strip().isascii() and value.strip().isdigit():
            return int(value.strip())
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, (retry_at - _utc_now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return 2 ** attempt

def _today_cutoff() -> datetime:
    n = now_kst()
    return n.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_subreddit(name: str, max_items: int = MAX_REDDIT_ITEMS) -> list[dict]:
    """오늘 Reddit RSS에서 본문을 보존하고 요청 실패는 호출자에게 전달한다."""
    url = f"https://www.reddit.com/r/{name}/top.rss?t=day"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.version or (feed.bozo and not feed.entries):
        raise ValueError("Invalid Reddit feed")
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
        link = getattr(entry, "link", "")
        # RSS의 작성자·[link]·[comments] 메타데이터는 본문이 아니다.
        candidates = [part.get("value", "") for part in entry.get("content", [])]
        candidates.append(entry.get("summary", ""))
        bodies = []
        for html in candidates:
            soup = BeautifulSoup(html or "", "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            bodies.append(" ".join(body.get_text(" ", strip=True) for body in soup.select(".md")))
        content = max(bodies, key=len, default="")
        items.append({
            "title": title,
            "url": link,
            "source": f"r/{name}",
            "summary": "",
            "content": content,
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_reddit() -> dict:
    """선택 소스의 결과를 구분하고 429 대기 예산을 subreddit 전체에 적용한다. 캐시는 쓰지 않는다."""
    all_items = []
    sources = []
    waited = 0
    rate_limited = False
    for n, name in enumerate(REDDIT_SUBREDDITS):
        result = {"name": f"r/{name}", "status": "failed", "count": 0, "attempts": 0,
                  "retry_wait_seconds": 0}
        sources.append(result)
        if rate_limited:
            result["status"] = "skipped_rate_limit"
            continue
        if n:
            sleep(1)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result["attempts"] = attempt
            try:
                items = fetch_subreddit(name)
                all_items.extend(items)
                result.update(status="success", count=len(items), http_status=200)
                result.pop("error_type", None)
                break
            except Exception as error:
                response = getattr(error, "response", None)
                code = response.status_code if response is not None else None
                result.update(http_status=code, error_type=type(error).__name__)
                if code != 429:
                    break
                delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                result["retry_after_seconds"] = delay
                if attempt == MAX_ATTEMPTS or waited + delay > MAX_RETRY_WAIT:
                    result["reason"] = "retries_exhausted" if attempt == MAX_ATTEMPTS else "wait_budget_exceeded"
                    rate_limited = True
                    break
                sleep(delay)
                waited += delay
                result["retry_wait_seconds"] += delay
        print(f"[Reddit] {result['name']} {result['status']} count={result['count']} attempts={result['attempts']}")
    successes = sum(result["status"] == "success" for result in sources)
    status = "success" if successes == len(sources) else ("partial" if successes else "failed")
    return {"items": all_items, "sources": sources, "status": status}
