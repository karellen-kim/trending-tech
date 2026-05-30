import re
import requests
from bs4 import BeautifulSoup
from config import SCRAPER_SOURCES, MAX_SCRAPER_ITEMS

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _strip_category_prefix(text: str) -> str:
    return re.sub(r'^[A-Z]{2,}', '', text).strip()

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
        })
        if len(items) >= max_items:
            break
    return items

def fetch_alibaba(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    resp = requests.get("https://www.alibabacloud.com/blog", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("https://www.alibabacloud.com/blog/"):
            continue
        # 목록 페이지 자체 링크 제거
        if href.rstrip("/") == "https://www.alibabacloud.com/blog":
            continue
        if href in seen:
            continue
        title = a.get_text(strip=True)
        if len(title) < 15:
            continue
        seen.add(href)
        items.append({
            "title": title,
            "url": href,
            "source": "Alibaba Cloud Blog",
            "summary": "",
        })
        if len(items) >= max_items:
            break
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
