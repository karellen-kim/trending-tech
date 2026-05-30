import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from config import DOCS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS
from sources.github import fetch_trending
from sources.hackernews import fetch_top_stories
from sources.rss import fetch_all_blogs
from sources.arxiv import fetch_all_papers
from summarizer import summarize_item, filter_important_papers
from renderer import render_daily_page, render_index_page
from notifier import send_slack


def _add_summaries(items: list[dict], content_key: str) -> list[dict]:
    for item in items:
        content = item.get(content_key) or item.get("description") or item.get("abstract") or ""
        item["summary"] = summarize_item(item.get("title") or item.get("name", ""), content)
    return items


def collect(today: str) -> dict:
    print(f"[{today}] 수집 시작")
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_gh = ex.submit(fetch_trending)
        f_hn = ex.submit(fetch_top_stories)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        github, hn, blogs, papers = f_gh.result(), f_hn.result(), f_bl.result(), f_ar.result()
    print(f"  GitHub:{len(github)} HN:{len(hn)} Blogs:{len(blogs)} Papers:{len(papers)}")
    papers = filter_important_papers(papers, max_items=MAX_PAPER_ITEMS)
    return {"date": today, "github": github, "hn": hn, "blogs": blogs, "papers": papers}


def summarize(data: dict) -> dict:
    print("[요약] 시작")
    data["github"] = _add_summaries(data["github"], "description")
    data["hn"] = _add_summaries(data["hn"], "title")
    data["papers"] = _add_summaries(data["papers"], "abstract")
    data["blogs"] = _add_summaries(data["blogs"], "summary")
    return data


def save_html(data: dict) -> list[str]:
    DOCS_DIR.mkdir(exist_ok=True)
    today = data["date"]

    (DOCS_DIR / f"{today}.html").write_text(render_daily_page(data), encoding="utf-8")
    print(f"[HTML] docs/{today}.html 저장")

    highlights = (
        [i.get("name", "") for i in data["github"][:2]] +
        [i.get("title", "") for i in data["hn"][:2]]
    )
    (DOCS_DIR / f"{today}.json").write_text(
        json.dumps({"date": today, "highlights": highlights}, ensure_ascii=False),
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


def git_commit_push(date_str: str) -> None:
    subprocess.run(["git", "add", f"docs/{date_str}.html", f"docs/{date_str}.json", "docs/index.html"], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: {date_str} trends"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("[Git] 커밋 + 푸시 완료")


def main():
    today = str(date.today())
    data = collect(today)
    data = summarize(data)
    highlights = save_html(data)
    git_commit_push(today)
    send_slack(SLACK_WEBHOOK_URL, today, highlights)
    print(f"[완료] {today}")


if __name__ == "__main__":
    main()
