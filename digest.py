"""일·주·월 요약 데이터를 모으는 로더.

일별 페이지의 해석(today_take)과 ★ 글(important_links)을 주간이 모으고,
주간 해석(week_take)을 월간이 모은다.

예전에 만든 페이지에는 JSON 필드가 없으므로 HTML 에서 파싱하는 폴백을 둔다.
"""
import json
import re
from datetime import date, datetime

from config import DOCS_DIR

_HEADLINE = re.compile(r'<p class="take-headline">(.*?)</p>', re.S)
_BODY = re.compile(r'<p class="take-body">(.*?)</p>', re.S)
_IMPORTANT = re.compile(r'<div class="item important">(.*?)(?:</details>|</div>\s*</div>)', re.S)
_LINK = re.compile(r'<div class="item-link"><a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_NAME = re.compile(r'<span class="item-name">(?:<span class="item-star"[^>]*>★</span>)?(.*?)</span>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return " ".join(_TAG.sub("", s or "").replace("&amp;", "&").split())


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_day_html(date_str: str) -> dict:
    """예전 일별 페이지에서 해석과 ★ 글을 읽어낸다."""
    f = DOCS_DIR / f"{date_str}.html"
    if not f.exists():
        return {}
    try:
        h = f.read_text(encoding="utf-8")
    except Exception:
        return {}
    m = _HEADLINE.search(h)
    if not m:
        return {}
    b = _BODY.search(h)
    links = []
    for blk in _IMPORTANT.findall(h):
        url = ""
        text = ""
        lm = _LINK.search(blk)
        if lm:
            url, text = lm.group(1), _clean(lm.group(2))
        nm = _NAME.search(blk)
        if nm:
            text = _clean(nm.group(1)) or text
        if url and text:
            links.append({"text": text, "url": url})
    return {"date": date_str, "headline": _clean(m.group(1)),
            "body": _clean(b.group(1)) if b else "", "links": links}


def load_day(date_str: str) -> dict:
    """일별 해석과 ★ 글. JSON 우선, 없으면 HTML 에서 파싱."""
    data = _read_json(DOCS_DIR / f"{date_str}.json")
    take = data.get("today_take") or {}
    if take.get("headline"):
        return {"date": date_str,
                "headline": take.get("headline", ""),
                "body": take.get("body", ""),
                "links": [l for l in (data.get("important_links") or []) if l.get("url")]}
    return _parse_day_html(date_str)


def load_week(days: list[dict]) -> list[dict]:
    """주간 페이지의 days 목록으로 그 주의 일별 해석을 모은다."""
    out = []
    for d in days:
        got = load_day(d.get("date", ""))
        if got.get("headline"):
            out.append(got)
    return out


def month_id(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_label(mid: str) -> str:
    y, m = mid.split("-")
    return f"{int(y)}년 {int(m)}월"


def load_month(year: int, month: int) -> list[dict]:
    """그 달에 속한 주간 해석들을 모은다. 주의 시작일이 그 달이면 포함한다."""
    out = []
    for f in sorted(DOCS_DIR.glob("????-W??.json")):
        data = _read_json(f)
        take = data.get("week_take") or {}
        if not take.get("headline"):
            continue
        days = data.get("days") or []
        if not days:
            continue
        try:
            # days 는 최신순으로 저장돼 있어 [0] 이 그 주의 마지막 날이다.
            # 월 경계에 걸친 주(예: 7/27~8/2)를 잘못된 달로 넣지 않으려면 min 을 쓴다.
            first = min(date.fromisoformat(d["date"]) for d in days)
        except Exception:
            continue
        if (first.year, first.month) != (year, month):
            continue
        out.append({"date": data.get("week_id", f.stem),
                    "headline": take.get("headline", ""),
                    "body": take.get("body", ""),
                    "links": [{"text": p.get("text", ""), "url": p.get("url", "")}
                              for p in (take.get("picks") or []) if p.get("url")]})
    return out
