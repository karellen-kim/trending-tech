import json
import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from datetime import date, timedelta, datetime

from config import (DOCS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS, SUMMARY_WORKERS, now_kst,
                    MAX_COMPANY_TOTAL, MAX_DEV_TOTAL, ENABLE_SVG, MAX_SVG_ITEMS,
                    ENABLE_NOTEBOOKLM)
from sources.github import fetch_trending
from sources.rss import fetch_all_blogs
from sources.arxiv import fetch_all_papers
from sources.scraper import fetch_all_scraped
from summarizer import (analyze_item, filter_important_papers, generate_highlights,
                        generate_highlight_links, generate_today_take, mark_important,
                        generate_week_take, generate_month_take)
import digest
from renderer import render_monthly_page
from svgmaker import add_svgs
from notebooklm import generate_audio_review
from renderer import render_daily_page, render_weekly_page, render_index_page
from notifier import send_slack


def _analyze_items(items: list[dict], content_key: str, filter_today: bool = True) -> list[dict]:
    """날짜 판정·제목 번역·요약을 항목당 claude 호출 1회로 처리하고,
    오늘 글이 아닌 항목은 리스트에서 제외한다."""
    if not items:
        return items
    today = str(now_kst().date())

    def one(item):
        # 짧은 RSS 요약이 truthy 라는 이유로 받아온 본문을 가리던 문제가 있었다
        # (Databricks 86자 요약이 1999자 본문을 덮었다). 가장 긴 것을 쓴다.
        cands = [item.get(content_key), item.get("content"),
                 item.get("description"), item.get("abstract")]
        content = max((c for c in cands if c), key=len, default="")
        title = item.get("title") or item.get("name", "")
        # 날짜를 거르지 않는 섹션(논문·GitHub)은 판정이 무의미하다.
        # 판정 프롬프트를 태우면 is_today=false 로 답하면서 요약·번역까지 빈 값이 되어
        # 렌더러가 영어 원문으로 폴백한다.
        verified = bool(item.get("date_verified")) or not filter_today
        result = analyze_item(title, content, item.get("pub_hint", "unknown"), today,
                              date_verified=verified)
        item["summary"] = result["summary"]
        item["title_ko"] = result["title_ko"]
        # 수집 단계에서 날짜를 확인한 항목은 그 값을 유지한다
        item["pub_date"] = item.get("pub_date") or result["pub_date"]
        item["is_today"] = result["is_today"]
        return item

    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as ex:
        analyzed = list(ex.map(one, items))
    if not filter_today:
        return analyzed
    kept = [i for i in analyzed if i.get("is_today")]
    print(f"  [날짜판정] {len(analyzed)}건 중 오늘 글 {len(kept)}건")
    return kept


def _load_yesterday_github() -> set[str]:
    yesterday = str(now_kst().date() - timedelta(days=1))
    jf = DOCS_DIR / f"{yesterday}.json"
    if not jf.exists():
        return set()
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
        return set(data.get("github_names", []))
    except Exception:
        return set()


def _load_recent_urls(days: int = 7) -> set[str]:
    """최근 페이지에 이미 실린 글 URL. COLLECT_DAYS 가 2 이상이면
    어제 글이 오늘 페이지에 다시 올라오므로 여기서 걸러낸다."""
    urls = set()
    for i in range(1, days + 1):
        jf = DOCS_DIR / f"{now_kst().date() - timedelta(days=i)}.json"
        if not jf.exists():
            continue
        try:
            urls |= set(json.loads(jf.read_text(encoding="utf-8")).get("seen_urls", []))
        except Exception:
            pass
    return urls


def collect(today: str) -> dict:
    print(f"[{today}] 수집 시작")
    yesterday_github = _load_yesterday_github()
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_gh = ex.submit(fetch_trending, "daily", yesterday_github)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        f_sc = ex.submit(fetch_all_scraped)
        github = f_gh.result()
        all_blogs = f_bl.result()
        papers = f_ar.result()
        scraped = f_sc.result()

    company_blogs = [b for b in all_blogs if b.get("category") == "company"]
    company_blogs += scraped
    dev_blogs = [b for b in all_blogs if b.get("category") != "company"]

    # 최근 페이지에 이미 실린 글은 제외 (COLLECT_DAYS 가 2 이상이라 어제 글이 다시 잡힌다)
    seen = _load_recent_urls()
    before = len(company_blogs) + len(dev_blogs)
    company_blogs = [b for b in company_blogs if b.get("url") not in seen]
    dev_blogs = [b for b in dev_blogs if b.get("url") not in seen]
    after = len(company_blogs) + len(dev_blogs)
    if before != after:
        print(f"  [중복제거] 이미 실린 글 {before - after}건 제외")

    papers = filter_important_papers(papers, max_items=MAX_PAPER_ITEMS)

    print(f"  GitHub:{len(github)} Company:{len(company_blogs)} "
          f"Dev:{len(dev_blogs)} Papers:{len(papers)}")

    return {
        "date": today,
        "github": github,
        "company_blogs": company_blogs,
        "dev_blogs": dev_blogs,
        "papers": papers,
    }


def summarize(data: dict) -> dict:
    print("[분석] 날짜판정 + 요약 시작")
    # 상한은 날짜 판정 뒤에 적용한다 — 판정 전에 자르면 오늘 글이 잘려나간다.
    data["company_blogs"] = _analyze_items(data["company_blogs"], "summary")[:MAX_COMPANY_TOTAL]
    data["dev_blogs"] = _analyze_items(data["dev_blogs"], "summary")[:MAX_DEV_TOTAL]
    data["papers"] = _analyze_items(data["papers"], "abstract", filter_today=False)
    data["github"] = _analyze_items(data["github"], "readme", filter_today=False)
    if ENABLE_SVG:
        print("[다이어그램] 생성 중...")
        add_svgs(data["company_blogs"], MAX_SVG_ITEMS)
        add_svgs(data["dev_blogs"], MAX_SVG_ITEMS)
        add_svgs(data["papers"], MAX_SVG_ITEMS)
    # 오늘 글들을 가로질러 읽은 해석 한 문장. 근거가 된 글은 목록에서 ★ 로 표시한다.
    take = generate_today_take(data)
    data["today_take"] = take
    if take:
        mark_important(data, take.get("refs", []))
        data["highlight_links"] = take.get("refs", [])
        data["highlights"] = [r["text"] for r in take.get("refs", [])]
        print(f"  [해석] {take['headline'][:50]}")
    else:
        # 해석 생성이 실패하면 기존 하이라이트 목록으로 되돌아간다
        links = generate_highlight_links(data)
        data["highlight_links"] = links
        data["highlights"] = [l["text"] for l in links] or generate_highlights(data)
    return data


def make_audio(data: dict) -> str:
    """하이라이트 링크로 새 노트북을 만들고 오디오 오버뷰 생성을 시킨다.
    성공하면 노트북 주소를 돌려준다. 파일은 내려받지 않는다 — 재생은 노트북에서 한다.
    실패해도 배치는 계속된다."""
    if not ENABLE_NOTEBOOKLM:
        return ""
    urls = [l.get("url") for l in data.get("highlight_links", []) if l.get("url")]
    if not urls:
        print("[Notebook] 하이라이트 링크가 없어 건너뜀")
        return ""
    try:
        print(f"[Notebook] 링크 {len(urls)}건으로 오디오 오버뷰 요청")
        # 노트북 제목은 "[Daily] YY.MM.DD 오늘의 해석" 으로 붙는다
        headline = (data.get("today_take") or {}).get("headline", "")
        yymmdd = date.fromisoformat(data["date"]).strftime("%y.%m.%d")
        return generate_audio_review(urls, title=headline, date_str=yymmdd)
    except Exception as e:
        print(f"[Notebook] 실패: {type(e).__name__}: {str(e)[:150]}")
        return ""


def load_month_takes() -> dict:
    """월간 페이지의 해석을 {"2026-07": {...}} 로 모은다. 목록에서도 보여주기 위해서다."""
    out = {}
    for jf in sorted(DOCS_DIR.glob("????-??.json")):
        try:
            take = json.loads(jf.read_text(encoding="utf-8")).get("month_take") or {}
        except Exception:
            continue
        if take.get("headline"):
            out[jf.stem] = {"headline": take["headline"], "body": take.get("body", "")}
    return out


def save_html(data: dict) -> list[str]:
    DOCS_DIR.mkdir(exist_ok=True)
    today = data["date"]

    (DOCS_DIR / f"{today}.html").write_text(render_daily_page(data), encoding="utf-8")
    print(f"[HTML] docs/{today}.html 저장")

    highlights = data.get("highlights") or [
        i.get("name", "") for i in data["github"][:2]
    ] + [i.get("title", "") for i in data["company_blogs"][:2]]

    (DOCS_DIR / f"{today}.json").write_text(
        json.dumps({
            "date": today,
            "highlights": highlights,
            "github_names": [i["name"] for i in data["github"]],
            "seen_urls": [i["url"] for k in ("company_blogs", "dev_blogs")
                          for i in data.get(k, []) if i.get("url")],
            # 주간·월간 해석이 이 필드들을 모아 쓴다
            "today_take": {k: v for k, v in (data.get("today_take") or {}).items()
                           if k in ("headline", "body")},
            "important_links": [{"text": l.get("text", ""), "url": l.get("url", "")}
                                for l in (data.get("highlight_links") or []) if l.get("url")],
        }, ensure_ascii=False),
        encoding="utf-8"
    )

    entries = []
    for jf in sorted(DOCS_DIR.glob("????-??-??.json")):
        try:
            entries.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception:
            pass
    (DOCS_DIR / "index.html").write_text(
        render_index_page(entries, load_month_takes()), encoding="utf-8")
    print("[HTML] docs/index.html 업데이트")
    return highlights


_DAY_KR = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]

def _week_id(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

def _week_label(week_id: str) -> str:
    y, w = week_id.split("-W")
    start = datetime.strptime(f"{y}-W{w}-1", "%G-W%V-%u").date()
    end = datetime.strptime(f"{y}-W{w}-7", "%G-W%V-%u").date()
    return f"{y}년 {start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"

def _week_highlights(day_takes: list[dict], limit: int = 5) -> list[dict]:
    """그 주 일별 페이지의 ★ 글을 모아 주간 하이라이트로 쓴다.
    예전에는 일요일 당일 데이터로 문장만 만들어 원문 링크가 없었다.
    하루에 몰리지 않게 날짜를 돌아가며 한 건씩 집는다."""
    out, seen = [], set()
    for tier in zip_longest(*[d.get("links", []) for d in day_takes]):
        for l in tier:
            url = (l or {}).get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"text": l.get("text", ""), "url": url})
            if len(out) >= limit:
                return out
    return out


def save_weekly_page(today: date, weekly_highlights: list[str] | None = None) -> None:
    wid = _week_id(today)
    # 이번 주에 속한 일별 JSON 수집
    days = []
    for jf in sorted(DOCS_DIR.glob("????-??-??.json")):
        try:
            d = date.fromisoformat(jf.stem)
            if _week_id(d) != wid:
                continue
            days.append({
                "date": str(d),
                "label": _DAY_KR[d.weekday()],
                "url": f"{d}.html",
            })
        except Exception:
            pass

    wjf = DOCS_DIR / f"{wid}.json"
    wdata = {}
    if wjf.exists():
        try:
            wdata = json.loads(wjf.read_text(encoding="utf-8"))
        except Exception:
            pass

    days = sorted(days, key=lambda x: x["date"])
    wdata.update({
        "week_id": wid,
        "week_label": _week_label(wid),
        "days": days,
    })
    # 그 주의 일별 해석을 모아 주간 해석을 만든다 (매일 갱신)
    day_takes = digest.load_week(days)
    if weekly_highlights is None:
        weekly_highlights = _week_highlights(day_takes)
    if weekly_highlights:
        wdata["highlights"] = weekly_highlights
    if day_takes:
        take = generate_week_take(day_takes)
        if take:
            wdata["week_take"] = take
            print(f"  [주간 해석] {take['headline'][:50]}")

    wjf.write_text(json.dumps(wdata, ensure_ascii=False), encoding="utf-8")
    (DOCS_DIR / f"{wid}.html").write_text(render_weekly_page(wdata), encoding="utf-8")
    print(f"[HTML] docs/{wid}.html 업데이트")

def save_monthly_page(today: date) -> str:
    """그 달의 주간 해석들을 모아 월간 페이지를 만든다. 만든 파일명을 돌려준다."""
    mid = digest.month_id(today.year, today.month)
    weeks = digest.load_month(today.year, today.month)
    if not weeks:
        return ""

    mdata = {}
    mjf = DOCS_DIR / f"{mid}.json"
    if mjf.exists():
        try:
            mdata = json.loads(mjf.read_text(encoding="utf-8"))
        except Exception:
            pass

    week_links = []
    for w in weeks:
        wid = w.get("date", "")
        wjf = DOCS_DIR / f"{wid}.json"
        label = wid
        if wjf.exists():
            try:
                label = json.loads(wjf.read_text(encoding="utf-8")).get("week_label", wid)
            except Exception:
                pass
        week_links.append({"label": label, "range": wid, "url": f"{wid}.html"})

    mdata.update({"month_id": mid, "month_label": digest.month_label(mid),
                  "weeks": week_links})

    take = generate_month_take(weeks)
    if take:
        mdata["month_take"] = take
        print(f"  [월간 해석] {take['headline'][:50]}")

    mjf.write_text(json.dumps(mdata, ensure_ascii=False), encoding="utf-8")
    (DOCS_DIR / f"{mid}.html").write_text(render_monthly_page(mdata), encoding="utf-8")
    print(f"[HTML] docs/{mid}.html 업데이트")
    return mid


def git_commit_push(date_str: str, month_id: str = "") -> None:
    wid = _week_id(date.fromisoformat(date_str))
    extra = [f"docs/{month_id}.html", f"docs/{month_id}.json"] if month_id else []
    subprocess.run(["git", "add", *extra,
        f"docs/{date_str}.html", f"docs/{date_str}.json",
        f"docs/{wid}.html", f"docs/{wid}.json",
        "docs/index.html"], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: {date_str} trends"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("[Git] 커밋 + 푸시 완료")


def _timeout_handler(signum, frame):
    print("[TIMEOUT] 1시간 초과, 강제 종료")
    raise SystemExit(1)


def main():
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(3600)

    today = now_kst().date()
    today_str = str(today)
    data = collect(today_str)
    data = summarize(data)

    # 오디오는 노트북에서 재생하므로, 성공하면 그 노트북 링크를 페이지에 건다
    notebook_url = make_audio(data)
    if notebook_url:
        data["audio_url"] = notebook_url
    highlights = save_html(data)

    # 주간 페이지 갱신 (매일). 하이라이트는 그 주 ★ 글에서 모은다.
    save_weekly_page(today)
    mid = save_monthly_page(today)

    if os.getenv("DRY") == "1":
        print("[DRY] 커밋·푸시·Slack 건너뜀")
    else:
        git_commit_push(today_str, mid)
        send_slack(SLACK_WEBHOOK_URL, today_str, highlights, data.get("today_take"))
    print(f"[완료] {today_str}")


if __name__ == "__main__":
    main()
