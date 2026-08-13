import json
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime

from config import (DOCS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS, SUMMARY_WORKERS,
                    MAX_COMPANY_TOTAL, MAX_DEV_TOTAL, ENABLE_SVG, MAX_SVG_ITEMS)
from sources.github import fetch_trending
from sources.rss import fetch_all_blogs
from sources.arxiv import fetch_all_papers
from sources.scraper import fetch_all_scraped
from summarizer import analyze_item, filter_important_papers, generate_highlights
from svgmaker import add_svgs
from renderer import render_daily_page, render_weekly_page, render_index_page
from notifier import send_slack


def _analyze_items(items: list[dict], content_key: str, filter_today: bool = True) -> list[dict]:
    """날짜 판정·제목 번역·요약을 항목당 claude 호출 1회로 처리하고,
    오늘 글이 아닌 항목은 리스트에서 제외한다."""
    if not items:
        return items
    today = str(date.today())

    def one(item):
        content = (item.get(content_key) or item.get("content") or
                   item.get("description") or item.get("abstract") or "")
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
    yesterday = str(date.today() - timedelta(days=1))
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
        jf = DOCS_DIR / f"{date.today() - timedelta(days=i)}.json"
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
    data["highlights"] = generate_highlights(data)
    return data


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
        }, ensure_ascii=False),
        encoding="utf-8"
    )

    entries = []
    for jf in sorted(DOCS_DIR.glob("????-??-??.json")):
        try:
            entries.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception:
            pass
    (DOCS_DIR / "index.html").write_text(render_index_page(entries), encoding="utf-8")
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
    return f"{y}년 {start.month}월 {int(w)}주 ({start.month}/{start.day} – {end.month}/{end.day})"

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

    wdata.update({
        "week_id": wid,
        "week_label": _week_label(wid),
        "days": sorted(days, key=lambda x: x["date"]),
    })
    if weekly_highlights is not None:
        wdata["highlights"] = weekly_highlights

    wjf.write_text(json.dumps(wdata, ensure_ascii=False), encoding="utf-8")
    (DOCS_DIR / f"{wid}.html").write_text(render_weekly_page(wdata), encoding="utf-8")
    print(f"[HTML] docs/{wid}.html 업데이트")

def git_commit_push(date_str: str) -> None:
    wid = _week_id(date.fromisoformat(date_str))
    subprocess.run(["git", "add",
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

    today = date.today()
    today_str = str(today)
    data = collect(today_str)
    data = summarize(data)
    highlights = save_html(data)

    # 주간 페이지 갱신 (매일)
    is_sunday = today.weekday() == 6
    weekly_hl = None
    if is_sunday:
        print("[주간 하이라이트] 생성 중...")
        weekly_hl = generate_highlights(data)  # 당일 데이터 기반, 필요시 주간 집계로 확장
    save_weekly_page(today, weekly_hl)

    git_commit_push(today_str)
    send_slack(SLACK_WEBHOOK_URL, today_str, highlights)
    print(f"[완료] {today_str}")


if __name__ == "__main__":
    main()
