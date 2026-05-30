import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timezone, timedelta
from config import SCRAPER_SOURCES, MAX_SCRAPER_ITEMS

KST = timezone(timedelta(hours=9))
_MONTH_MAP = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

def _is_today(date_str: str) -> bool:
    """'May 26, 2026' 형식 날짜가 오늘(KST)인지 확인"""
    try:
        m = re.search(r'(\w{3})\s+(\d{1,2}),?\s+(\d{4})', date_str)
        if not m:
            return False
        month, day, year = _MONTH_MAP.get(m.group(1), 0), int(m.group(2)), int(m.group(3))
        today = datetime.now(KST).date()
        return date(year, month, day) == today
    except Exception:
        return False

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
        items.append({
            "title": title,
            "url": href,
            "source": "Uber Engineering",
            "summary": "",
            "content": _fetch_article_text(href),
        })
        if len(items) >= max_items:
            break
    return items

def fetch_alibaba(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    resp = requests.get("https://www.alibabacloud.com/blog", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    date_pattern = re.compile(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}')
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("https://www.alibabacloud.com/blog/"):
            continue
        if href.rstrip("/") == "https://www.alibabacloud.com/blog" or href in seen:
            continue
        title = a.get_text(strip=True)
        if len(title) < 15:
            continue
        # 부모 요소에서 날짜 찾아 오늘 날짜만 포함
        parent = a.parent
        date_found, is_today = False, False
        for _ in range(6):
            if parent is None:
                break
            m = date_pattern.search(parent.get_text(" ", strip=True))
            if m:
                date_found = True
                is_today = _is_today(m.group())
                break
            parent = parent.parent
        if date_found and not is_today:
            continue
        seen.add(href)
        items.append({
            "title": title,
            "url": href,
            "source": "Alibaba Cloud Blog",
            "summary": "",
            "content": _fetch_article_text(href),
        })
        if len(items) >= max_items:
            break
    return items

def fetch_spotify(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    from datetime import date
    resp = requests.get("https://engineering.atspotify.com/", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    today = date.today()
    # URL 패턴: /YYYY/M/slug — 현재 월 또는 직전 월 기준
    pattern = re.compile(r'^/(\d{4})/(\d{1,2})/')
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = pattern.match(href)
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        # 이번 달 또는 지난달만 포함
        if not ((y == today.year and mo == today.month) or
                (y == today.year and mo == today.month - 1) or
                (today.month == 1 and y == today.year - 1 and mo == 12)):
            continue
        full_url = f"https://engineering.atspotify.com{href}"
        if full_url in seen:
            continue
        title = a.get_text(strip=True)
        if len(title) < 15:
            continue
        seen.add(full_url)
        items.append({
            "title": title,
            "url": full_url,
            "source": "Spotify Engineering",
            "summary": "",
            "content": _fetch_article_text(full_url),
        })
        if len(items) >= max_items:
            break
    return items

_SCRAPERS = {
    "Uber Engineering": fetch_uber,
    "Alibaba Cloud Blog": fetch_alibaba,
    "Spotify Engineering": fetch_spotify,
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
