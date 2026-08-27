#!/usr/bin/env python3
"""예전 페이지에 빠진 해석(오늘의·이 주의·이 달의)을 채운다.

해석 기능은 8월 중순에 붙었고 그 전 페이지에는 해석이 없다.
수집 원본은 남아 있지 않으므로 이미 실린 글 목록을 HTML 에서 다시 읽어
해석만 새로 만들어 넣는다. 페이지의 나머지(요약·다이어그램)는 건드리지 않는다.

이미 해석이 있는 날짜·주차는 건너뛴다. 중간에 끊겨도 다시 돌리면 이어진다.

    python backfill.py days     # 일별
    python backfill.py weeks    # 주차 (일별을 먼저 채워야 한다)
    python backfill.py months   # 월별 (주차를 먼저 채워야 한다)
    python backfill.py all
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import digest
from config import DOCS_DIR, SUMMARY_WORKERS
from renderer import _e, _section_html, render_weekly_page
from summarizer import generate_today_take, generate_week_take

# 예전 페이지에는 해석 블록이 없으니 그 CSS 도 함께 넣어야 한다
_TAKE_CSS = """
  /* ── 오늘의 해석 (backfill) ── */
  .take { background: var(--accent-wash); border: 1px solid oklch(0.92 0.04 50); padding: 1.4rem 1.5rem; }
  .take-headline { font-size: 1.12rem; font-weight: 700; line-height: 1.5; letter-spacing: -0.02em;
    color: var(--ink); }
  .take-body { margin-top: 0.9rem; font-size: 0.9rem; line-height: 1.75; color: var(--ink-soft); }
  .take-refs { margin-top: 1.1rem; padding-top: 0.9rem; border-top: 1px solid oklch(0.92 0.04 50);
    font-size: 0.78rem; line-height: 1.9; color: var(--ink-faint); }
  .take-refs span { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.1em;
    text-transform: uppercase; margin-right: 0.6rem; }
  .take-refs a { color: var(--accent-deep); text-decoration: none; }
  .take-refs a:hover { text-decoration: underline; }
"""

_SECTION = re.compile(r'<div class="section[^"]*" id="([^"]+)">')
_ITEM_NAME = re.compile(
    r'<div class="item-name">(?:<span class="item-star"[^>]*>★</span>)?\s*'
    r'<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_ITEM_META = re.compile(r'<div class="item-meta">(.*?)</div>', re.S)
_TAG = re.compile(r"<[^>]+>")

# 페이지 섹션 id → summarizer 가 보는 데이터 키
_SECTION_KEY = {
    "tech-blog": "company_blogs",
    "dev-blogs": "dev_blogs",
    "hn-reddit": "dev_blogs",
    "papers": "papers",
    "arxiv": "papers",
    "github": "github",
}


def _clean(s: str) -> str:
    return " ".join(_TAG.sub("", s or "")
                    .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&#39;", "'").split())


def parse_items(html: str) -> dict:
    """페이지에 실린 글을 섹션별로 되읽는다. generate_today_take 가 보는 모양으로 맞춘다."""
    data = {"company_blogs": [], "dev_blogs": [], "papers": [], "github": []}
    bounds = [(m.group(1), m.start(), m.end()) for m in _SECTION.finditer(html)]
    for i, (sid, _, end) in enumerate(bounds):
        key = _SECTION_KEY.get(sid)
        if not key:
            continue
        stop = bounds[i + 1][1] if i + 1 < len(bounds) else len(html)
        block = html[end:stop]
        metas = _ITEM_META.findall(block)
        for n, (url, title) in enumerate(_ITEM_NAME.findall(block)):
            title = _clean(title)
            if not title:
                continue
            data[key].append({
                "title": title,
                "title_ko": title,
                "name": title,
                "url": url,
                "source": _clean(metas[n]) if n < len(metas) else "",
            })
    return data


def _take_html(take: dict) -> str:
    refs = ""
    if take.get("refs"):
        links = " · ".join(
            f'<a href="{r["url"]}" target="_blank" rel="noopener">{_e(r["text"])}</a>'
            if r.get("url") else _e(r["text"]) for r in take["refs"])
        refs = f'<div class="take-refs"><span>근거</span>{links}</div>'
    body = f'<p class="take-body">{_e(take["body"])}</p>' if take.get("body") else ""
    return _section_html("today-take", "★", "오늘의 해석",
                         f'<div class="take"><p class="take-headline">{_e(take["headline"])}</p>'
                         f'{body}{refs}</div>')


def _insert_into_page(html: str, take: dict) -> str:
    """해석 섹션을 하이라이트 섹션 앞에 끼워 넣고, 없는 CSS 를 채운다."""
    if "take-headline" not in html:
        html = html.replace("</style>", _TAKE_CSS + "</style>", 1)
    anchor = _SECTION.search(html)
    if not anchor:
        raise ValueError("섹션을 찾지 못함")
    at = anchor.start()
    return html[:at] + _take_html(take) + html[at:]


def backfill_day(date_str: str) -> bool:
    if digest.load_day(date_str).get("headline"):
        return False
    hf = DOCS_DIR / f"{date_str}.html"
    jf = DOCS_DIR / f"{date_str}.json"
    if not hf.exists():
        print(f"  {date_str} HTML 없음, 건너뜀")
        return False

    html = hf.read_text(encoding="utf-8")
    data = parse_items(html)
    total = sum(len(v) for v in data.values())
    if not total:
        print(f"  {date_str} 글 0건, 건너뜀")
        return False

    take = generate_today_take(data)
    if not take.get("headline"):
        print(f"  {date_str} 해석 생성 실패")
        return False

    hf.write_text(_insert_into_page(html, take), encoding="utf-8")

    jdata = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {"date": date_str}
    jdata["today_take"] = {"headline": take["headline"], "body": take.get("body", "")}
    jdata["important_links"] = [{"text": r.get("text", ""), "url": r.get("url", "")}
                                for r in take.get("refs", []) if r.get("url")]
    jf.write_text(json.dumps(jdata, ensure_ascii=False), encoding="utf-8")

    print(f"  {date_str} ({total}건) {take['headline'][:46]}")
    return True


def backfill_week(wid: str) -> bool:
    jf = DOCS_DIR / f"{wid}.json"
    if not jf.exists():
        return False
    wdata = json.loads(jf.read_text(encoding="utf-8"))
    day_takes = digest.load_week(wdata.get("days") or [])
    if not day_takes:
        print(f"  {wid} 일별 해석이 없어 건너뜀")
        return False

    changed = []
    # 해석은 없을 때만 새로 만든다 — 여기만 LLM 을 태운다
    if not (wdata.get("week_take") or {}).get("headline"):
        take = generate_week_take(day_takes)
        if take and take.get("headline"):
            wdata["week_take"] = take
            changed.append(take["headline"][:46])
        else:
            print(f"  {wid} 해석 생성 실패")

    if not changed:
        return False

    jf.write_text(json.dumps(wdata, ensure_ascii=False), encoding="utf-8")
    (DOCS_DIR / f"{wid}.html").write_text(render_weekly_page(wdata), encoding="utf-8")
    print(f"  {wid} ({len(day_takes)}일) " + " / ".join(changed))
    return True


def run_days() -> int:
    """날짜끼리는 서로를 참조하지 않으므로 나눠서 돌린다.
    한 건이 4분 걸려 순차로는 50건에 3시간이 넘는다."""
    targets = [f.stem for f in sorted(DOCS_DIR.glob("????-??-??.json"))
               if not digest.load_day(f.stem).get("headline")]
    print(f"[일별] 시작 — 대상 {len(targets)}건, 동시 {SUMMARY_WORKERS}")

    def one(d):
        try:
            return bool(backfill_day(d))
        except Exception as e:
            print(f"  {d} 오류: {type(e).__name__}: {str(e)[:120]}")
            return False

    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as ex:
        n = sum(ex.map(one, targets))
    print(f"[일별] {n}건 채움")
    return n


def run_weeks() -> int:
    print("[주차] 시작")
    n = 0
    for f in sorted(DOCS_DIR.glob("????-W??.json")):
        try:
            n += bool(backfill_week(f.stem))
        except Exception as e:
            print(f"  {f.stem} 오류: {type(e).__name__}: {str(e)[:120]}")
    print(f"[주차] {n}건 채움")
    return n


def run_months() -> int:
    from main import save_monthly_page
    print("[월별] 시작")
    months = sorted({f.stem[:7] for f in DOCS_DIR.glob("????-??-??.json")})
    n = 0
    for mid in months:
        y, m = mid.split("-")
        try:
            if save_monthly_page(date(int(y), int(m), 15)):
                n += 1
        except Exception as e:
            print(f"  {mid} 오류: {type(e).__name__}: {str(e)[:120]}")
    print(f"[월별] {n}건 생성")
    return n


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("days", "all"):
        run_days()
    if what in ("weeks", "all"):
        run_weeks()
    if what in ("months", "all"):
        run_months()
