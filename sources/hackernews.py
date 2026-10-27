import re
from datetime import date, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from config import MAX_HN_ITEMS, now_kst

HN_URL = "https://news.ycombinator.com/"
FRONT_URL = urljoin(HN_URL, "front")


def fetch_top_stories(day: str | None = None) -> list[dict]:
    """공식 past 페이지에 표시된 순서대로 해당 날짜의 상위 글을 가져온다."""
    if day is None:
        day = (now_kst().date() - timedelta(days=1)).isoformat()
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("HN day must be an ISO date (YYYY-MM-DD)")
    resp = requests.get(FRONT_URL, params={"day": day}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for row in soup.select("tr.athing"):
        title = row.select_one(".titleline > a")
        rank = row.select_one(".rank")
        story_id = row.get("id", "")
        rank_match = re.fullmatch(r"(\d+)\.", rank.get_text(strip=True)) if rank else None
        if not title or not title.get_text(strip=True) or not story_id.isdigit() or not rank_match:
            continue
        hn_url = urljoin(HN_URL, f"item?id={story_id}")
        metadata = row.find_next_sibling("tr")
        subtext = metadata.select_one(".subtext") if metadata else None
        score = subtext.select_one(".score") if subtext else None
        score_match = re.search(r"\d+", score.get_text()) if score else None
        comments = 0
        for link in subtext.select("a") if subtext else []:
            match = re.fullmatch(r"(\d+)\s+comments?", link.get_text(" ", strip=True))
            if match:
                comments = int(match.group(1))
        items.append({
            "title": title.get_text(" ", strip=True),
            "url": urljoin(HN_URL, title.get("href") or hn_url),
            "points": int(score_match.group()) if score_match else 0,
            "comments": comments,
            "hn_url": hn_url,
            "source": "HN",
            "rank": int(rank_match.group(1)),
            "source_date": day,
        })
        if len(items) >= MAX_HN_ITEMS:
            break
    if not items:
        raise ValueError(f"No valid HN stories found for {day}")
    return items
