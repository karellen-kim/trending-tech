import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timezone, timedelta
from config import SCRAPER_SOURCES, MAX_SCRAPER_ITEMS, COLLECT_DAYS

KST = timezone(timedelta(hours=9))
_MONTH_MAP = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

def _parse_date(date_str: str) -> date | None:
    """'May 26, 2026' / 'August 12, 2025'처럼 축약·전체 월 이름 모두 지원. 못 읽으면 None."""
    try:
        m = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', date_str or "")
        if not m:
            return None
        month = _MONTH_MAP.get(m.group(1)[:3].capitalize(), 0)
        return date(int(m.group(3)), month, int(m.group(2)))
    except Exception:
        return None

def _is_today(date_str: str) -> bool:
    d = _parse_date(date_str)
    return d is not None and d == datetime.now(KST).date()

def _is_recent(date_str: str, days: int = COLLECT_DAYS) -> bool:
    """최근 days 일(오늘 포함) 이내인지. 날짜를 못 읽으면 False."""
    d = _parse_date(date_str)
    if d is None:
        return False
    today = datetime.now(KST).date()
    return today - timedelta(days=days - 1) <= d <= today

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _strip_category_prefix(text: str) -> str:
    # e.g. "RESEARCHMoirai" → "Moirai", "TECHApache" → "Apache"
    m = re.match(r'^[A-Z]{4,}(?=[A-Z][a-z])', text)
    if m:
        return text[m.end():].strip()
    # e.g. "TECHuReview" → "uReview"
    m = re.match(r'^[A-Z]{4,}(?=[a-z])', text)
    if m:
        return text[m.end():].strip()
    # e.g. "TECH BLOG Apache" → "Apache"
    return re.sub(r'^(?:[A-Z]{2,}\s+)+', '', text).strip()

def _fetch_article_text(url: str, max_chars: int = 2000) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        # 서버가 Content-Type 에 charset 을 안 주면 requests 는 ISO-8859-1 로 가정한다.
        # 그대로 두면 한글이 mojibake 로 깨진다 (LY Corp 실측).
        if resp.encoding is None or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup.body
        if not container:
            return ""
        text = " ".join(container.get_text(" ", strip=True).split())
        return text[:max_chars]
    except Exception:
        return ""

_UBER_DATE_PATTERN = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+\d{1,2},\s+\d{4}\b'
)

def _fetch_article_date(url: str) -> str:
    """글 페이지에서 가장 먼저 나오는 날짜 문자열. 못 찾으면 빈 문자열."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        m = _UBER_DATE_PATTERN.search(resp.text)
        return m.group() if m else ""
    except Exception:
        return ""

def _fetch_uber_article(url: str, max_chars: int = 2000) -> tuple[str, str]:
    """Uber 블로그 개별 글의 발행일 텍스트와 본문을 한 번의 요청으로 함께 가져온다.
    발행일은 본문 상단(제목 바로 앞)에 있고 하단 관련글 목록에도 날짜가 나오므로,
    페이지에서 가장 먼저 매칭되는 날짜 문자열을 이 글의 발행일로 취급한다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        date_match = _UBER_DATE_PATTERN.search(resp.text)
        pub_date = date_match.group() if date_match else ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup.body
        text = " ".join(container.get_text(" ", strip=True).split()) if container else ""
        return pub_date, text[:max_chars]
    except Exception:
        return "", ""

def fetch_uber(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    resp = requests.get("https://eng.uber.com/", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "uber.com/blog/" not in href or href in seen:
            continue
        raw_text = a.get_text(strip=True)
        if len(raw_text) < 15:
            continue
        title = _strip_category_prefix(raw_text)
        # 너무 짧거나 순수 UI 텍스트 제거
        if len(title) < 10:
            continue
        seen.add(href)
        # eng.uber.com 목록 페이지에는 발행일이 없어(고정/추천 글도 섞여 나옴) 개별 글을 열어 확인.
        # 날짜를 읽었으면 여기서 거르고, 못 읽은 것만 LLM 판정으로 넘긴다.
        pub_date, content = _fetch_uber_article(href)
        if pub_date and not _is_recent(pub_date):
            continue
        items.append({
            "title": title,
            "url": href,
            "source": "Uber Engineering",
            "summary": "",
            "content": content,
            "pub_hint": pub_date or "unknown",
            "date_verified": bool(pub_date),
            "pub_date": str(_parse_date(pub_date)) if pub_date else "",
        })
        if len(items) >= max_items:
            break
    return items

def fetch_alibaba(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    resp = requests.get("https://www.alibabacloud.com/blog", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, candidates = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("https://www.alibabacloud.com/blog/"):
            continue
        if href.rstrip("/") == "https://www.alibabacloud.com/blog" or href in seen:
            continue
        title = a.get_text(strip=True)
        if len(title) < 15:
            continue
        seen.add(href)
        candidates.append((title, href))
        if len(candidates) >= max_items:
            break

    # 목록 페이지에는 날짜 없는 카드가 많아(실측 20/34) 개별 글에서 발행일 문자열을 가져온다.
    # 날짜를 읽었으면 여기서 거르고, 못 읽은 것만 LLM 판정으로 넘긴다.
    items = []
    for title, href in candidates:
        pub_date = _fetch_article_date(href)
        if pub_date and not _is_recent(pub_date):
            continue
        items.append({
            "title": title,
            "url": href,
            "source": "Alibaba Cloud Blog",
            "summary": "",
            "content": _fetch_article_text(href),
            "pub_hint": pub_date or "unknown",
            "date_verified": bool(pub_date),
            "pub_date": str(_parse_date(pub_date)) if pub_date else "",
        })
    return items

_SCRAPERS = {
    "Uber Engineering": fetch_uber,
    "Alibaba Cloud Blog": fetch_alibaba,
}

def fetch_all_scraped() -> list[dict]:
    all_items = []
    for source in SCRAPER_SOURCES:
        fn = _SCRAPERS.get(source["name"])
        if not fn:
            continue
        try:
            all_items.extend(fn())
        except Exception as e:
            print(f"[Scraper] {source['name']} 실패: {e}")
    return all_items
