import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime

from config import DOCS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS
from sources.github import fetch_trending
from sources.hackernews import fetch_top_stories
from sources.rss import fetch_all_blogs
from sources.arxiv import fetch_all_papers
from sources.reddit import fetch_all_reddit
from sources.scraper import fetch_all_scraped
from summarizer import summarize_item, filter_important_papers, generate_highlights, translate_title
from renderer import render_daily_page, render_weekly_page, render_index_page
from notifier import send_slack


def _add_summaries(items: list[dict], content_key: str) -> list[dict]:
    for item in items:
        content = (item.get(content_key) or item.get("content") or
                   item.get("description") or item.get("abstract") or "")
        title = item.get("title") or item.get("name", "")
        item["summary"] = summarize_item(title, content)
        item["title_ko"] = translate_title(title)
    return items


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


def collect(today: str) -> dict:
    print(f"[{today}] 수집 시작")
    yesterday_github = _load_yesterday_github()
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_gh = ex.submit(fetch_trending, "daily", yesterday_github)
        f_hn = ex.submit(fetch_top_stories)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        f_rd = ex.submit(fetch_all_reddit)
        f_sc = ex.submit(fetch_all_scraped)
        github = f_gh.result()
        hn = f_hn.result()
        all_blogs = f_bl.result()
        papers = f_ar.result()
        reddit = f_rd.result()
        scraped = f_sc.result()

    company_blogs = [b for b in all_blogs if b.get("category") == "company"]
    company_blogs += scraped
    dev_blogs = [b for b in all_blogs if b.get("category") != "company"]

    papers = filter_important_papers(papers, max_items=MAX_PAPER_ITEMS)

    print(f"  GitHub:{len(github)} HN:{len(hn)} Company:{len(company_blogs)} "
          f"Dev:{len(dev_blogs)} Papers:{len(papers)} Reddit:{len(reddit)}")

    return {
        "date": today,
        "github": github,
        "hn": hn,
        "company_blogs": company_blogs,
        "dev_blogs": dev_blogs,
        "papers": papers,
        "reddit": reddit,
    }


def summarize(data: dict) -> dict:
    print("[요약] 시작")
    data["github"] = _add_summaries(data["github"], "description")
    data["hn"] = _add_summaries(data["hn"], "title")
    data["company_blogs"] = _add_summaries(data["company_blogs"], "summary")
    data["dev_blogs"] = _add_summaries(data["dev_blogs"], "summary")
    data["papers"] = _add_summaries(data["papers"], "abstract")
    data["reddit"] = _add_summaries(data["reddit"], "title")
    data["highlights"] = generate_highlights(data)
    return data


def save_html(data: dict) -> list[str]:
    DOCS_DIR.mkdir(exist_ok=True)
    today = data["date"]

    (DOCS_DIR / f"{today}.html").write_text(render_daily_page(data), encoding="utf-8")
    print(f"[HTML] docs/{today}.html 저장")

    highlights = data.get("highlights") or [
        i.get("name", "") for i in data["github"][:2]
    ] + [i.get("title", "") for i in data["hn"][:2]]

    (DOCS_DIR / f"{today}.json").write_text(
        json.dumps({
            "date": today,
            "highlights": highlights,
            "github_names": [i["name"] for i in data["github"]],
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


def main():
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
