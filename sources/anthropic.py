"""Anthropic의 공식 날짜별 목록과 개별 본문을 수집한다."""
from datetime import datetime, date, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config import COLLECT_DAYS, KST, MAX_SCRAPER_ITEMS, now_kst

_ORIGIN = 'https://www.anthropic.com'
_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; TrendingTech/1.0)'}


def _official_url(href: str, base: str) -> str | None:
    try:
        url = urlsplit(urljoin(base, href))
        if (url.scheme != 'https' or url.hostname not in {'anthropic.com', 'www.anthropic.com'}
                or url.username is not None or url.password is not None or url.port not in {None, 443}):
            return None
        return urlunsplit(('https', 'www.anthropic.com', url.path or '/', url.query, ''))
    except ValueError:
        return None


def _date(value: str) -> date | None:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            return parsed.astimezone(KST).date()
    except ValueError:
        pass
    for fmt in ('%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _html(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    if _official_url(response.url or url, url) is None:
        raise ValueError('Anthropic response redirected outside official origin')
    response.encoding = 'utf-8'
    return BeautifulSoup(response.text, 'html.parser')


def _listing(soup: BeautifulSoup, url: str) -> list[tuple[date, str, str]]:
    rows = soup.select('main [data-listing-row]')
    candidates = {}
    for row in rows:
        heading = row.find(['h2', 'h3'])
        link = (heading.find('a', href=True) or heading.find_parent('a', href=True)) if heading else None
        time = row.find('time')
        published = _date(time.get('datetime') or time.get_text(' ', strip=True)) if time else None
        href = _official_url(link['href'], url) if link else None
        title = heading.get_text(' ', strip=True) if heading else ''
        if published and href and title:
            if href in candidates and candidates[href][0] != published:
                raise ValueError('Conflicting Anthropic listing dates')
            candidates.setdefault(href, (published, title, href))
    if not candidates:
        raise ValueError('Anthropic listing has no valid dated article rows')
    return sorted(candidates.values(), key=lambda item: item[0], reverse=True)


def _article(url: str, published: date) -> tuple[date, str]:
    soup = _html(url)
    meta = soup.select_one('meta[property="article:published_time"]')
    time = soup.select_one('article > header time')
    raw = meta.get('content', '') if meta else (time.get('datetime') or time.get_text(' ', strip=True) if time else '')
    canonical = _date(raw)
    try:
        calendar = datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
    except ValueError:
        calendar = canonical
    # 목록의 날짜만 있는 표기는 원문 달력일일 수 있어 시간대 경계를 함께 검증한다.
    if canonical is None or published not in {canonical, calendar}:
        raise ValueError('Anthropic article publication date does not match listing')
    body = soup.select_one('article div[class*="_body"]')
    if body is None or body.select_one('.post-text') is None:
        raise ValueError('Anthropic article body is missing')
    for element in body.select('script,style,nav,footer,header,aside,[class*="related"],[class*="Related"]'):
        element.decompose()
    text = ' '.join(body.get_text(' ', strip=True).split())
    if not text:
        raise ValueError('Anthropic article body is empty')
    return canonical, text[:2000]


def _fetch(section: str, source: str, max_items: int) -> list[dict]:
    if max_items <= 0:
        return []
    url = f'{_ORIGIN}/{section}'
    candidates = _listing(_html(url), url)
    today = now_kst().date()
    start = today - timedelta(days=COLLECT_DAYS - 1)
    recent = [item for item in candidates if start - timedelta(days=1) <= item[0] <= today][:min(max_items, MAX_SCRAPER_ITEMS)]
    items = []
    for published, title, href in recent:
        canonical, content = _article(href, published)
        if start <= canonical <= today:
            items.append({'title': title, 'url': href, 'source': source, 'summary': '',
                          'content': content, 'pub_hint': canonical.isoformat(),
                          'pub_date': canonical.isoformat(), 'date_verified': True})
    return items


def fetch_anthropic_engineering(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    return _fetch('engineering', 'Anthropic Engineering', max_items)


def fetch_anthropic_news(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    return _fetch('news', 'Anthropic News', max_items)
