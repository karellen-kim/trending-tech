import feedparser
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta, time
from config import now_kst
from config import RSS_SOURCES, MAX_BLOG_ITEMS, MAX_BODY_FETCH, RSS_WORKERS, COLLECT_DAYS
from sources.scraper import _fetch_article_text

KST = timezone(timedelta(hours=9))
_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}
MIN_CONTENT = 150   # summarizer 가 요약을 포기하는 하한

def _plain_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.select("script, style"):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())

def _text_len(html: str) -> int:
    return len(_plain_text(html))

def enrich_with_body(items: list[dict], max_fetch: int = MAX_BODY_FETCH,
                     *, min_content: int = MIN_CONTENT) -> list[dict]:
    """기준보다 짧은 미리보기의 원문을 조회하고 더 긴 본문만 보존한다.
    블로그는 요약 입력 한도까지 보강하고 커뮤니티는 기존 150자 기준을 쓴다."""
    targets = [i for i in items if max(_text_len(i.get("summary", "")),
                                      _text_len(i.get("content", ""))) < min_content][:max_fetch]
    if not targets:
        return items

    def one(item):
        existing_size = max(_text_len(item.get("summary", "")),
                            _text_len(item.get("content", "")))
        body = _fetch_article_text(item["url"])
        if _text_len(body) >= MIN_CONTENT and _text_len(body) > existing_size:
            item["content"] = body

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, targets))
    return items

def _get_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def _pub_hint(entry) -> str:
    """날짜를 못 읽은 항목을 LLM이 판정할 때 쓰는 근거 문자열."""
    raw = (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()
    pub = _get_date(entry)
    if pub is None:
        return raw or "unknown"
    kst = pub.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    return f"{kst} KST (피드 원문: {raw})" if raw else f"{kst} KST"

def _recent_range(days: int = COLLECT_DAYS) -> tuple[datetime, datetime]:
    """(N일 전 00:00 KST, 내일 00:00 KST)를 UTC로. 상한이 있어야 발행일을
    미래로 찍은 글이 매일 다시 올라오지 않는다."""
    start_kst = now_kst().replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_kst - timedelta(days=days - 1)
    end = start_kst + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS, **kwargs) -> list[dict]:
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    start, end = _recent_range()
    # 피드는 최신순이므로 앞에서 max_items 건만 본다.
    # 발행일이 있으면 여기서 코드로 거른다 — 실측상 171건 전부 날짜 파싱이 되므로
    # 이 단계에서 LLM 호출 대상이 171건에서 몇 건으로 줄어든다.
    # 날짜를 못 읽은 항목만 pub_hint 를 달아 통과시키고 summarizer.analyze_item 이 판정한다.
    for entry in feed.entries[:max_items]:
        pub = _get_date(entry)
        if pub is not None and not (start <= pub < end):
            continue
        summary = getattr(entry, "summary", "") or ""
        feed_content = [_plain_text(part.get("value", ""))
                        for part in (getattr(entry, "content", None) or [])]
        content = max([_plain_text(summary), *feed_content], key=len)
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "source": name,
            "summary": summary[:500],
            "content": content,
            "pub_hint": _pub_hint(entry),
            "date_verified": pub is not None,
            "pub_date": pub.astimezone(KST).strftime("%Y-%m-%d") if pub else "",
            "category": kwargs.get("category", "dev"),
        })
    return items

def fetch_all_blogs() -> list[dict]:
    def one(source):
        try:
            return fetch_rss_entries(
                source["name"], source["url"], category=source.get("category", "dev")
            )
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
            return []

    all_items = []
    with ThreadPoolExecutor(max_workers=RSS_WORKERS) as ex:
        for items in ex.map(one, RSS_SOURCES):
            all_items.extend(items)
    return enrich_with_body(all_items, min_content=1500)
