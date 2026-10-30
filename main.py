import json
import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime

from config import (DOCS_DIR, LOGS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS, SUMMARY_WORKERS, now_kst,
                    MAX_HN_ITEMS, MAX_REDDIT_ITEMS, MAX_COMPANY_TOTAL, MAX_DEV_TOTAL,
                    ENABLE_NOTEBOOKLM)
from sources.github import fetch_trending
from sources.hackernews import fetch_top_stories
from sources.reddit import fetch_all_reddit
from sources.rss import fetch_all_blogs, enrich_with_body, _plain_text
from sources.arxiv import fetch_all_papers
from sources.scraper import fetch_all_scraped
from summarizer import (LlmCallError, _log_llm_event, analyze_item, filter_important_papers, generate_highlights,
                        generate_highlight_links, generate_today_take, mark_important,
                        generate_week_take, generate_month_take)
import digest
from renderer import render_monthly_page
from notebooklm import generate_audio_review
from renderer import render_daily_page, render_weekly_page, render_index_page
from notifier import send_slack
from run_receipt import RunReceipt, record_stage


def _analyze_items(items: list[dict], content_key: str, filter_today: bool = True) -> list[dict]:
    """날짜 판정·제목 번역·요약을 항목당 Codex 호출 1회로 처리하고,
    오늘 글이 아닌 항목은 리스트에서 제외한다."""
    if not items:
        return items
    today = str(now_kst().date())

    def one(item):
        # HTML 속성 길이로 부풀린 미리보기가 실제 본문을 가리지 않게 비교한다.
        cands = [item.get(content_key), item.get("content"), item.get("summary"),
                 item.get("description"), item.get("abstract")]
        content = max((_plain_text(c) for c in cands if c), key=len, default="")
        title = item.get("title") or item.get("name", "")
        # 날짜를 거르지 않는 섹션(논문·GitHub)은 판정이 무의미하다.
        # 판정 프롬프트를 태우면 is_today=false 로 답하면서 요약·번역까지 빈 값이 되어
        # 렌더러가 영어 원문으로 폴백한다.
        verified = bool(item.get("date_verified")) or not filter_today
        context = f"{title} {item.get('url', '')}".strip()
        try:
            result = analyze_item(title, content, item.get("pub_hint", "unknown"), today,
                                  date_verified=verified)
        except LlmCallError as error:
            raise LlmCallError(error.kind, error.message, context=context) from error
        if not isinstance(result, dict) or type(result.get("is_today")) is not bool:
            raise LlmCallError("invalid_response", "is_today must be a boolean", context=context)
        retained = verified or result["is_today"]
        if retained:
            if not isinstance(result.get("title_ko"), str) or not result["title_ko"].strip():
                raise LlmCallError("missing_output", "Required title translation is empty", context=context)
            if content_key != "title" and len(content.strip()) >= 150:
                if not isinstance(result.get("summary"), str) or not result["summary"].strip():
                    raise LlmCallError("missing_output", "Required summary is empty", context=context)
        item["summary"] = result.get("summary", "")
        item["title_ko"] = result.get("title_ko", "")
        # 수집 단계에서 날짜를 확인한 항목은 그 값을 유지한다
        item["pub_date"] = item.get("pub_date") or result.get("pub_date", "unknown")
        item["is_today"] = result["is_today"]
        return item

    ex = ThreadPoolExecutor(max_workers=SUMMARY_WORKERS)
    futures = {ex.submit(one, item): index for index, item in enumerate(items)}
    analyzed = [None] * len(items)
    try:
        for future in as_completed(futures):
            analyzed[futures[future]] = future.result()
    except BaseException as error:
        cancelled = sum(future.cancel() for future in futures)
        _log_llm_event("analysis_failed", kind=getattr(error, "kind", "interrupted"),
                       total=len(items), completed=sum(item is not None for item in analyzed),
                       cancelled=cancelled, error=str(error) if isinstance(error, LlmCallError) else type(error).__name__)
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        ex.shutdown(wait=True)
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


def collect(today: str, hn_day: str | None = None) -> dict:
    print(f"[{today}] 수집 시작")
    hn_day = hn_day or (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    date.fromisoformat(hn_day)
    yesterday_github = _load_yesterday_github()
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_gh = ex.submit(fetch_trending, "daily", yesterday_github)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        f_sc = ex.submit(fetch_all_scraped)
        f_hn = ex.submit(fetch_top_stories, day=hn_day)
        f_rd = ex.submit(fetch_all_reddit)
        github = f_gh.result()
        all_blogs = f_bl.result()
        papers = f_ar.result()
        scraped = f_sc.result()
        # 커뮤니티는 부가 섹션이다. 한 소스가 죽어도 배치는 계속된다.
        try:
            hn = f_hn.result()
            hn_status = {"required": False, "status": "success", "count": len(hn)}
        except Exception as error:
            print(f"[HN] 수집 실패: {type(error).__name__}")
            hn = []
            hn_status = {"required": False, "status": "failed", "count": 0,
                         "error_type": type(error).__name__}
        try:
            reddit_result = f_rd.result()
            reddit = reddit_result["items"]
            reddit_status = {"required": False, **{key: reddit_result[key] for key in ("status", "sources")},
                             "count": len(reddit)}
        except Exception as error:
            print(f"[Reddit] 수집 실패: {type(error).__name__}")
            reddit = []
            reddit_status = {"required": False, "status": "failed", "count": 0,
                             "error_type": type(error).__name__}

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
    # HN past의 공식 순위는 과거 URL 중복 여부와 무관하게 유지한다.
    hn = hn[:MAX_HN_ITEMS]
    reddit_urls = set(seen)
    unique_reddit = []
    for item in reddit:
        url = item.get("url", "")
        if url and url in reddit_urls:
            continue
        if url:
            reddit_urls.add(url)
        unique_reddit.append(item)
        if len(unique_reddit) >= MAX_REDDIT_ITEMS:
            break
    reddit = unique_reddit

    print(f"  GitHub:{len(github)} Company:{len(company_blogs)} "
          f"Dev:{len(dev_blogs)} Papers:{len(papers)} HN:{len(hn)} Reddit:{len(reddit)}")

    return {
        "date": today,
        "github": github,
        "company_blogs": company_blogs,
        "dev_blogs": dev_blogs,
        "papers": papers,
        "hn": hn,
        "reddit": reddit,
        "hn_date": hn_day,
        "source_status": {"hn": hn_status, "reddit": reddit_status},
    }


def summarize(data: dict) -> dict:
    print("[분석] 날짜판정 + 요약 시작")
    # 상한은 날짜 판정 뒤에 적용한다 — 판정 전에 자르면 오늘 글이 잘려나간다.
    data["company_blogs"] = _analyze_items(data["company_blogs"], "summary")[:MAX_COMPANY_TOTAL]
    data["dev_blogs"] = _analyze_items(data["dev_blogs"], "summary")[:MAX_DEV_TOTAL]
    data["papers"] = _analyze_items(data["papers"], "abstract", filter_today=False)
    data["github"] = _analyze_items(data["github"], "readme", filter_today=False)
    body_keys = ("content", "summary", "description", "abstract")
    for section in ("hn", "reddit"):
        items = data.get(section, [])
        # 이미 제공된 본문은 그대로 사용하고, 본문이 없는 링크만 읽는다.
        targets = [item for item in items if item.get("url") and
                   not any(len((item.get(key) or "").strip()) >= 150 for key in body_keys)]
        enrich_with_body(targets)
        body_available = [any(len((item.get(key) or "").strip()) >= 150 for key in body_keys)
                          for item in items]
        analyzed = _analyze_items(items, "content", filter_today=False)
        for item, has_body in zip(analyzed, body_available):
            if not has_body:
                item["summary"] = ""
        if section in data:
            data[section] = analyzed
    # 과거 JSON을 수동 재처리하는 경우의 호환 경로.
    if "community" in data:
        data["community"] = _analyze_items(data["community"], "title", filter_today=False)
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
    existing_url = data.get("audio_url", "")
    if not existing_url:
        try:
            existing_url = json.loads((DOCS_DIR / f"{data['date']}.json").read_text(encoding="utf-8")).get("audio_url", "")
        except (OSError, ValueError):
            pass
    if existing_url:
        return existing_url
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
            "seen_urls": [i["url"] for k in ("company_blogs", "dev_blogs", "hn", "reddit", "community")
                          for i in data.get(k, []) if i.get("url")],
            # 주간·월간 해석이 이 필드들을 모아 쓴다
            "today_take": {k: v for k, v in (data.get("today_take") or {}).items()
                           if k in ("headline", "body")},
            "important_links": [{"text": l.get("text", ""), "url": l.get("url", "")}
                                for l in (data.get("highlight_links") or []) if l.get("url")],
            **({"audio_url": data["audio_url"]} if data.get("audio_url") else {}),
            **{key: data[key] for key in ("hn", "reddit", "hn_date") if key in data},
            **({"source_status": data["source_status"]} if "source_status" in data else {}),
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

def save_weekly_page(today: date) -> None:
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

    days = sorted(days, key=lambda x: x["date"], reverse=True)
    wdata.update({
        "week_id": wid,
        "week_label": _week_label(wid),
        "days": days,
    })
    # 그 주의 일별 해석을 모아 주간 해석을 만든다 (매일 갱신)
    day_takes = digest.load_week(days)
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
    weeks = list(reversed(digest.load_month(today.year, today.month)))
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


def git_commit_push(date_str: str, month_id: str = "") -> dict:
    """Git 커밋과 push를 수행하며 push 실패에도 커밋 증거를 보존한다."""
    wid = _week_id(date.fromisoformat(date_str))
    extra = [f"docs/{month_id}.html", f"docs/{month_id}.json"] if month_id else []
    subprocess.run(["git", "add", *extra,
        f"docs/{date_str}.html", f"docs/{date_str}.json",
        f"docs/{wid}.html", f"docs/{wid}.json",
        "docs/index.html"], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: {date_str} trends"], check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    record_stage("git", "running", commit_sha=sha, committed=True, pushed=False)
    subprocess.run(["git", "push"], check=True)
    print("[Git] 커밋 + 푸시 완료")
    return {"status": "success", "commit_sha": sha, "committed": True, "pushed": True}


def _timeout_handler(signum, frame):
    print("[TIMEOUT] 6시간 초과, 강제 종료")
    raise SystemExit(1)


def _termination_handler(signum, frame):
    """SIGTERM을 종료 영수증을 남길 수 있는 프로세스 중단으로 바꾼다."""
    raise SystemExit(128 + signum)


def main(hn_day: str | None = None):
    """시작부터 게시까지 실행 영수증을 남기고 중단·부분 결과를 구분한다."""
    today = now_kst().date()
    today_str = str(today)
    with RunReceipt(LOGS_DIR / "runs", today_str) as run:
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGALRM, signal.SIGTERM)}
        previous_alarm = signal.alarm(0)
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.signal(signal.SIGTERM, _termination_handler)
            signal.alarm(6 * 3600)
            _run_daily(today, today_str, hn_day, run)
            run.require_finished_llm()
        finally:
            signal.alarm(0)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            if previous_alarm:
                signal.alarm(previous_alarm)


def _run_daily(today: date, today_str: str, hn_day: str | None, run: RunReceipt) -> None:
    """기존 일일 흐름에서 실제로 통과한 단계와 게시 결과만 기록한다."""
    run.stage("collection", "running")
    data = collect(today_str, hn_day=hn_day) if hn_day is not None else collect(today_str)
    run.sources(data.get("source_status", {}))
    run.stage("collection", "success")
    run.stage("summary", "running")
    data = summarize(data)
    if any(data.get(section) for section in ("company_blogs", "dev_blogs", "papers", "github", "hn", "reddit", "community")):
        take = data.get("today_take") or {}
        if not isinstance(take, dict) or not isinstance(take.get("headline"), str) or not take["headline"].strip():
            raise LlmCallError("missing_output", "Required today_take headline is empty", context=today_str)
    run.require_finished_llm()
    run.stage("summary", "success")

    # 오디오는 노트북에서 재생하므로, 성공하면 그 노트북 링크를 페이지에 건다
    notebook_url = make_audio(data)
    if notebook_url:
        data["audio_url"] = notebook_url
    run.stage("artifacts", "running")
    highlights = save_html(data)

    # 주간 페이지 갱신 (매일). 하이라이트는 그 주 ★ 글에서 모은다.
    save_weekly_page(today)
    mid = save_monthly_page(today)
    run.require_finished_llm()
    daily_json = DOCS_DIR / f"{today_str}.json"
    daily_html = DOCS_DIR / f"{today_str}.html"
    saved = json.loads(daily_json.read_text(encoding="utf-8"))
    if saved.get("date") != today_str or not daily_html.read_text(encoding="utf-8").strip():
        raise RuntimeError("Daily artifacts are missing or invalid")
    run.stage("artifacts", "success", json=str(daily_json), html=str(daily_html))

    if os.getenv("DRY") == "1":
        run.stage("git", "skipped", reason="dry_run")
        run.stage("slack", "skipped", reason="dry_run")
        run.outcome = "dry_run"
        print("[DRY] 커밋·푸시·Slack 건너뜀")
    else:
        run.stage("git", "running")
        git = git_commit_push(today_str, mid)
        run.stage("git", **git)
        run.stage("slack", "running")
        slack = send_slack(SLACK_WEBHOOK_URL, today_str, highlights, data.get("today_take"))
        run.stage("slack", **slack)
        complete = slack["status"] == "success" and all(
            result["status"] == "success" for result in data.get("source_status", {}).values())
        run.outcome = "published" if complete else "partial"
    print(f"[{run.outcome}] {today_str}")


if __name__ == "__main__":
    main()
