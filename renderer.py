from collections import defaultdict

_FAVICON = """<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='5' fill='%231a1714'/%3E%3Cpolyline points='3,26 10,18 17,22 24,10 29,6' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpolyline points='22,5 29,6 28,13' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='5' fill='%231a1714'/%3E%3Cpolyline points='3,26 10,18 17,22 24,10 29,6' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpolyline points='22,5 29,6 28,13' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">"""

_FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">"""

_BASE_CSS = """<style>
  :root {
    --paper: oklch(1 0 0); --paper-deep: oklch(0.985 0 0);
    --ink: oklch(0.18 0.015 260); --ink-soft: oklch(0.38 0.012 260); --ink-faint: oklch(0.58 0.008 260);
    --rule: oklch(0.90 0.005 260); --accent: oklch(0.55 0.16 38);
    --accent-deep: oklch(0.40 0.14 38); --accent-wash: oklch(0.96 0.025 50);
    --sans: "IBM Plex Sans KR", -apple-system, sans-serif;
    --mono: "JetBrains Mono", ui-monospace, monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 15px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
</style>"""

_DAILY_CSS = """<style>
  body { max-width: 900px; margin: 0 auto; padding: 0 2rem 4rem; }

  /* ── 상단 바 ── */
  .top-bar { display: flex; align-items: center; justify-content: space-between; padding: 1rem 0; border-bottom: 1px solid var(--rule); margin-bottom: 2.5rem; }
  .back-btn { font-size: 0.78rem; font-weight: 500; color: var(--ink-soft); text-decoration: none; border: 1px solid var(--rule); padding: 0.28rem 0.7rem; }
  .back-btn:hover { border-color: var(--accent); color: var(--accent-deep); }

  /* ── 페이지 제목 ── */
  .page-meta { font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.4rem; }
  h1 { font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1; margin-bottom: 2rem; }
  h1 em { font-style: normal; color: var(--accent); }

  /* ── 섹션 네비게이션 (sticky) ── */
  .page-nav { position: sticky; top: 0; background: var(--paper); border-bottom: 1px solid var(--rule); border-top: 1px solid var(--rule); padding: 0; margin-bottom: 3rem; z-index: 20; display: flex; flex-wrap: wrap; }
  .nav-link { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); text-decoration: none; padding: 0.55rem 1rem; border-right: 1px solid var(--rule); white-space: nowrap; transition: all 0.12s; }
  .nav-link:hover { color: var(--accent-deep); background: var(--accent-wash); }
  .nav-link:last-child { border-right: none; }

  /* ── 섹션 ── */
  .section { margin-bottom: 4rem; scroll-margin-top: 48px; }

  /* ── 섹션 헤더 ── */
  .section-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; padding-bottom: 0.8rem; border-bottom: 2px solid var(--ink); }
  .section-icon { font-family: var(--mono); font-size: 0.62rem; background: var(--ink); color: var(--paper); padding: 0.2rem 0.5rem; letter-spacing: 0.06em; flex-shrink: 0; }
  .section-title { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.02em; color: var(--ink); }
  .section-count { font-family: var(--mono); font-size: 0.6rem; color: var(--ink-faint); margin-left: auto; letter-spacing: 0.08em; }

  /* ── 하이라이트 섹션 ── */
  .highlight-section .section-header { border-bottom-color: var(--accent); }
  .highlight-section .section-icon { background: var(--accent); }
  .highlight-list { list-style: none; padding: 0; background: var(--accent-wash); border: 1px solid oklch(0.92 0.04 50); }
  .highlight-list li { font-size: 0.93rem; color: var(--ink); padding: 0.7rem 1rem 0.7rem 2.2rem; position: relative; border-bottom: 1px solid oklch(0.92 0.04 50); line-height: 1.5; }
  .highlight-list li:last-child { border-bottom: none; }
  .highlight-list li::before { content: "→"; position: absolute; left: 0.8rem; color: var(--accent); font-family: var(--mono); font-size: 0.75rem; top: 0.8rem; }

  /* ── 아이템 ── */
  .item { display: grid; grid-template-columns: 1fr auto; gap: 1rem; padding: 1.1rem 0; border-bottom: 1px solid var(--rule); }
  .item:last-child { border-bottom: none; }
  .item-left { min-width: 0; }
  .item-name { font-weight: 600; font-size: 0.97rem; margin-bottom: 0.2rem; line-height: 1.4; }
  .item-name a { color: var(--ink); text-decoration: none; }
  .item-name a:hover { color: var(--accent-deep); }
  .item-meta { font-family: var(--mono); font-size: 0.63rem; color: var(--ink-faint); margin-bottom: 0.5rem; letter-spacing: 0.04em; }
  .item-summary { font-size: 0.875rem; color: var(--ink-soft); line-height: 1.7; }
  .item-arrow { font-family: var(--mono); font-size: 0.85rem; color: var(--ink-faint); padding-top: 0.15rem; flex-shrink: 0; }
  .item-arrow a { color: inherit; text-decoration: none; }
  .item-arrow a:hover { color: var(--accent); }

  @media (max-width: 600px) {
    body { padding: 0 1rem 3rem; }
    .nav-link { font-size: 0.6rem; padding: 0.45rem 0.65rem; }
  }
</style>"""

_INDEX_CSS = """<style>
  /* ── 레이아웃 ── */
  body { display: flex; min-height: 100vh; }

  /* ── 사이드바 (기존 유지) ── */
  .sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--rule); position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 2rem 0; }
  .sidebar-header { padding: 0 1.4rem 1.4rem; border-bottom: 1px solid var(--rule); margin-bottom: 1rem; }
  .s-label { font-size: 0.62rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; margin-bottom: 0.4rem; }
  .s-title { font-size: 1rem; font-weight: 700; color: var(--ink); letter-spacing: -0.02em; }
  .year-btn { width: 100%; padding: 0.7rem 1.4rem; display: block; cursor: pointer; background: none; border: none; font-family: var(--sans); text-align: left; font-size: 0.9rem; font-weight: 500; color: var(--ink-soft); border-left: 2px solid transparent; transition: all 0.12s; }
  .year-btn:hover { background: var(--paper-deep); }
  .year-btn.active { background: var(--accent-wash); border-left-color: var(--accent); color: var(--accent-deep); font-weight: 600; }

  /* ── 메인 ── */
  .main { flex: 1; overflow-y: auto; min-width: 0; }
  .year-section { display: none; }

  /* ── 히어로 ── */
  .main-hero { padding: clamp(2rem,5vw,4rem) clamp(1.5rem,4vw,3.5rem) clamp(2.5rem,5vw,4rem); max-width: 900px; position: relative; }
  .main-hero::before { content: ""; position: absolute; top: 2rem; left: clamp(1.5rem,4vw,3.5rem); right: clamp(1.5rem,4vw,3.5rem); height: 1px; background: var(--ink); }
  .meta-row { display: flex; justify-content: space-between; align-items: baseline; padding-top: 2.5rem; font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-soft); font-weight: 500; }
  .meta-row span:last-child { color: var(--accent-deep); }
  .main-title { font-size: clamp(2.4rem,6vw,4.8rem); line-height: 0.95; font-weight: 600; margin-top: clamp(1.5rem,4vw,2.5rem); letter-spacing: -0.035em; color: var(--ink); }
  .main-title em { font-style: normal; font-weight: 300; color: var(--accent-deep); }
  .hero-grid { margin-top: clamp(2rem,4vw,3.5rem); display: grid; grid-template-columns: repeat(auto-fit,minmax(120px,1fr)); gap: 1px; background: var(--rule); border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
  .hero-grid > div { background: var(--paper); padding: 1rem 1.25rem; }
  .hero-grid .k { display: block; font-size: 0.63rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; margin-bottom: 0.3rem; }
  .hero-grid .v { font-size: 1.05rem; color: var(--ink); font-weight: 600; letter-spacing: -0.01em; }
  .hero-grid .v small { font-size: 0.72rem; color: var(--ink-soft); margin-left: 0.2rem; font-weight: 400; }

  /* ── 월 섹션 ── */
  .m-section { padding: clamp(2.5rem,5vw,4rem) clamp(1.5rem,4vw,3.5rem); border-top: 1px solid var(--rule); max-width: 900px; }
  .section-head { display: grid; grid-template-columns: auto 1fr; gap: clamp(1rem,3vw,2.2rem); align-items: baseline; margin-bottom: clamp(1.5rem,3vw,2.5rem); }
  .section-num { font-size: clamp(2.8rem,6vw,4.8rem); line-height: 0.85; color: var(--accent); font-weight: 200; letter-spacing: -0.04em; }
  .section-titles { border-left: 1px solid var(--ink); padding-left: clamp(0.9rem,2.5vw,1.8rem); padding-top: 0.4rem; }
  .section-kicker { font-size: 0.72rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--accent-deep); font-weight: 600; margin-bottom: 0.5rem; }
  .section-title { font-size: clamp(1.5rem,2.8vw,2rem); line-height: 1.15; font-weight: 600; letter-spacing: -0.025em; }

  /* ── 주차 리스트 ── */
  .notes { border-top: 2px solid var(--ink); }
  .note { display: grid; grid-template-columns: 3.5rem 1fr auto; gap: clamp(0.8rem,2vw,2rem); align-items: center; padding: clamp(1.2rem,3vw,2rem) 0; border-bottom: 1px solid var(--rule); text-decoration: none; color: var(--ink); transition: padding 0.3s cubic-bezier(0.22,1,0.36,1), background 0.2s ease; position: relative; }
  .note:hover { padding-left: 0.8rem; padding-right: 0.8rem; background: var(--paper-deep); }
  .note::after { content: ""; position: absolute; left: 0; bottom: -1px; height: 1px; width: 0; background: var(--accent); transition: width 0.4s cubic-bezier(0.22,1,0.36,1); }
  .note:hover::after { width: 100%; }
  .note .n { font-size: 0.78rem; color: var(--accent); font-weight: 400; letter-spacing: 0.06em; font-family: var(--mono); }
  .note .body { min-width: 0; }
  .note .body h3 { font-size: clamp(1.1rem,1.8vw,1.35rem); font-weight: 600; line-height: 1.25; letter-spacing: -0.02em; color: var(--ink); margin-bottom: 0.3rem; }
  .note .body h3 em { font-style: normal; color: var(--accent-deep); font-weight: 400; }
  .note .body p { color: var(--ink-soft); font-size: 0.88rem; font-weight: 300; line-height: 1.55; }
  .note .meta { display: flex; flex-direction: column; align-items: flex-end; gap: 0.4rem; font-size: 0.7rem; color: var(--ink-faint); text-align: right; white-space: nowrap; }
  .note .meta .tag { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent-deep); padding: 0.2rem 0.5rem; border: 1px solid var(--accent); background: var(--accent-wash); }
  .note .arrow { font-family: var(--mono); color: var(--ink); font-weight: 500; font-size: 1rem; transition: transform 0.3s cubic-bezier(0.22,1,0.36,1); }
  .note:hover .arrow { transform: translateX(5px); color: var(--accent-deep); }

  @media (prefers-reduced-motion: no-preference) {
    .m-section, .note { animation: rise 0.6s cubic-bezier(0.22,1,0.36,1) both; }
    @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  }
  @media (max-width: 640px) {
    .note { grid-template-columns: 3rem 1fr; }
    .note .meta { grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; align-items: flex-start; }
    .note .arrow { display: none; }
  }
</style>"""

_MONTH_NAMES = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}

def _e(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _item_html(name: str, url: str, meta: str, summary: str, name_ko: str = "") -> str:
    display_name = name_ko if name_ko and name_ko.strip() else name
    return f"""<div class="item">
  <div class="item-left">
    <div class="item-name"><a href="{url}" target="_blank" rel="noopener">{_e(display_name)}</a></div>
    <div class="item-meta">{_e(meta)}</div>
    <div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>
  </div>
  <div class="item-arrow"><a href="{url}" target="_blank" rel="noopener">&rarr;</a></div>
</div>"""

_SECTIONS_META = [
    ("highlights",    "★",    "오늘의 하이라이트"),
    ("tech-blog",     "기술",  "기술 블로그"),
    ("dev-blogs",     "개발",  "개발자 블로그 &amp; SNS"),
    ("papers",        "논문",  "AI / LLM 논문"),
    ("hn-reddit",     "커뮤",  "Hacker News &amp; Reddit"),
    ("github",        "코드",  "GitHub 트렌딩"),
]

def _section_html(sid: str, icon: str, title: str, items_html: str, count: int = 0) -> str:
    count_html = f'<span class="section-count">{count}개</span>' if count else ""
    extra_cls = " highlight-section" if sid == "highlights" else ""
    return f"""<div class="section{extra_cls}" id="{sid}">
  <div class="section-header">
    <span class="section-icon">{icon}</span>
    <span class="section-title">{title}</span>
    {count_html}
  </div>
  {items_html}
</div>"""

def render_daily_page(data: dict) -> str:
    date = data["date"]
    y, m, d = date.split("-")

    # 섹션별 콘텐츠 생성
    highlights = data.get("highlights", [])
    company_blogs = data.get("company_blogs", [])
    dev_blogs = data.get("dev_blogs", [])
    papers = data.get("papers", [])
    hn_reddit = data.get("hn", []) + data.get("reddit", [])
    github = data.get("github", [])

    sections = ""

    if highlights:
        rows = "".join(f'<li>{_e(h)}</li>' for h in highlights)
        sections += _section_html("highlights", "★", "오늘의 하이라이트",
            f'<ul class="highlight-list">{rows}</ul>')

    if company_blogs:
        sections += _section_html("tech-blog", "TECH", "기술 블로그", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""), i.get("title_ko",""))
            for i in company_blogs), len(company_blogs))

    if dev_blogs:
        sections += _section_html("dev-blogs", "DEV", "개발자 블로그 &amp; SNS", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""), i.get("title_ko",""))
            for i in dev_blogs), len(dev_blogs))

    if papers:
        sections += _section_html("papers", "PAPER", "AI / LLM 논문", "".join(
            _item_html(i["title"], i["url"], "arXiv", i.get("summary", i.get("abstract","")), i.get("title_ko",""))
            for i in papers), len(papers))

    if hn_reddit:
        sections += _section_html("hn-reddit", "커뮤", "Hacker News &amp; Reddit", "".join(
            _item_html(
                i.get("title",""), i["url"],
                f"{i.get('source','HN')} · {i.get('points',0)} pts" if "points" in i else i.get("source",""),
                i.get("summary",""), i.get("title_ko",""))
            for i in hn_reddit), len(hn_reddit))

    if github:
        sections += _section_html("github", "코드", "GitHub 트렌딩", "".join(
            _item_html(i["name"], i["url"], i.get("stars_today",""), i.get("summary", i.get("description","")))
            for i in github), len(github))

    # 존재하는 섹션만 nav에 포함
    section_ids = {
        "highlights": bool(highlights),
        "tech-blog": bool(company_blogs),
        "dev-blogs": bool(dev_blogs),
        "papers": bool(papers),
        "hn-reddit": bool(hn_reddit),
        "github": bool(github),
    }
    nav_links = "".join(
        f'<a href="#{sid}" class="nav-link">{title.replace("&amp;","&")}</a>'
        for sid, icon, title in _SECTIONS_META
        if section_ids.get(sid)
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{date} — Trending Tech</title>
{_FAVICON}
{_FONTS}
{_BASE_CSS}
{_DAILY_CSS}
</head>
<body>
<div class="top-bar">
  <a href="./index.html" class="back-btn">&larr; index</a>
  <span style="font-family:var(--mono);font-size:0.65rem;color:var(--ink-faint);letter-spacing:0.1em">TRENDING-TECH</span>
</div>
<div class="page-meta">{date}</div>
<h1><em>{d}</em> {_MONTH_NAMES[m]} {y}</h1>
<nav class="page-nav">{nav_links}</nav>
{sections}
</body>
</html>"""

def render_weekly_page(week_data: dict) -> str:
    """
    week_data: {
      "week_id": "2026-W22",
      "week_label": "2026년 5월 4주 (5/25 – 5/31)",
      "highlights": [...],          # 일요일에만 채워짐
      "days": [{"date":"2026-05-27", "label":"화요일", "url":"2026-05-27.html"}, ...]
    }
    """
    week_id = week_data["week_id"]
    label = week_data.get("week_label", week_id)
    highlights = week_data.get("highlights", [])
    days = week_data.get("days", [])

    hl_html = ""
    if highlights:
        rows = "".join(f'<li>{_e(h)}</li>' for h in highlights)
        hl_html = f"""<div class="section highlight-section" id="highlights">
  <div class="section-header">
    <span class="section-icon">★</span>
    <span class="section-title">주간 하이라이트</span>
  </div>
  <ul class="highlight-list">{rows}</ul>
</div>"""

    days_html = ""
    for d in days:
        days_html += f'<a href="./{d["url"]}" class="day-link"><span class="day-label">{d["label"]}</span><span class="day-date">{d["date"]}</span><span class="day-arrow">&rarr;</span></a>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{week_id} — Trending Tech</title>
{_FAVICON}
{_FONTS}
{_BASE_CSS}
{_DAILY_CSS}
<style>
  .days-section {{ margin-top: 3rem; }}
  .days-section-title {{ font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-faint); font-weight: 600; padding-bottom: 0.6rem; border-bottom: 2px solid var(--ink); margin-bottom: 0; }}
  .day-link {{ display: flex; align-items: center; gap: 1rem; padding: 0.9rem 0; border-bottom: 1px solid var(--rule); text-decoration: none; color: var(--ink); transition: background 0.1s; }}
  .day-link:last-child {{ border-bottom: none; }}
  .day-link:hover {{ color: var(--accent-deep); }}
  .day-label {{ font-weight: 600; font-size: 0.95rem; min-width: 4rem; }}
  .day-date {{ font-family: var(--mono); font-size: 0.72rem; color: var(--ink-faint); }}
  .day-arrow {{ font-family: var(--mono); font-size: 0.85rem; color: var(--ink-faint); margin-left: auto; }}
  .day-link:hover .day-arrow {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="top-bar">
  <a href="./index.html" class="back-btn">&larr; index</a>
  <span style="font-family:var(--mono);font-size:0.65rem;color:var(--ink-faint);letter-spacing:0.1em">TRENDING-TECH</span>
</div>
<div class="page-meta">{week_id}</div>
<h1><em>{label.split("(")[0].strip()}</em></h1>
{hl_html}
<div class="days-section">
  <div class="days-section-title">이번 주 일별 보기</div>
  {days_html}
</div>
</body>
</html>"""

def render_index_page(entries: list[dict]) -> str:
    from datetime import datetime

    def _week_id(d: str) -> str:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"

    def _week_range(week_id: str) -> tuple:
        y, w = week_id.split("-W")
        start = datetime.strptime(f"{y}-W{w}-1", "%G-W%V-%u").date()
        end = datetime.strptime(f"{y}-W{w}-7", "%G-W%V-%u").date()
        return f"{start.month}/{start.day}", f"{end.month}/{end.day}"

    # 연도 → 월 → 주차별 분류
    by_year = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for e in sorted(entries, key=lambda x: x["date"], reverse=True):
        y, mo, _ = e["date"].split("-")
        wid = _week_id(e["date"])
        by_year[y][mo][wid].append(e)

    years = sorted(by_year.keys(), reverse=True)

    # stats
    all_dates = sorted(e["date"] for e in entries)
    first_date = all_dates[0][:7].replace("-", ".") if all_dates else "—"
    last_date = all_dates[-1] if all_dates else "—"
    total_days = len(all_dates)

    sidebar = "".join(
        f'<button class="year-btn" data-year="{y}" onclick="showYear(\'{y}\')">{y}</button>'
        for y in years)

    year_sections = ""
    for y in years:
        months_html = ""
        for mo_idx, mo in enumerate(sorted(by_year[y].keys(), reverse=True), 1):
            notes_html = ""
            for wid in sorted(by_year[y][mo].keys(), reverse=True):
                week_entries = by_year[y][mo][wid]
                day_count = len(week_entries)
                w_num = wid.split("-W")[1]
                s, e_ = _week_range(wid)

                # 하이라이트 수집 (최대 2개)
                highlights = []
                for we in sorted(week_entries, key=lambda x: x["date"]):
                    highlights.extend(we.get("highlights", []))
                if highlights:
                    desc = "　·　".join(h[:40] + ("…" if len(h) > 40 else "") for h in highlights[:2])
                    desc_html = f'<p>{_e(desc)}</p>'
                else:
                    desc_html = f'<p>{s} – {e_} · {day_count}일</p>'

                notes_html += f"""<a class="note" href="./{wid}.html">
  <div class="n">W{w_num}</div>
  <div class="body">
    <h3>{int(mo)}월 <em>{w_num}주</em></h3>
    {desc_html}
  </div>
  <div class="meta">
    <span class="tag">{day_count}일</span>
    <span class="arrow">&rarr;</span>
  </div>
</a>"""

            months_html += f"""<div class="m-section">
  <div class="section-head">
    <div class="section-num">{mo:>02}</div>
    <div class="section-titles">
      <div class="section-kicker">{y}</div>
      <h2 class="section-title">{int(mo)}월 {_MONTH_NAMES[mo]}</h2>
    </div>
  </div>
  <div class="notes">{notes_html}</div>
</div>"""

        year_sections += f'<div class="year-section" id="year-{y}">{months_html}</div>'

    first_year = years[0] if years else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trending Tech</title>
{_FAVICON}
{_FONTS}
{_BASE_CSS}
{_INDEX_CSS}
</head>
<body>
<nav class="sidebar">
  <div class="sidebar-header">
    <div class="s-label">trending</div>
    <div class="s-title">tech</div>
  </div>
  {sidebar}
</nav>
<main class="main">
  <div class="main-hero">
    <div class="meta-row">
      <span>trending-tech &middot; archive</span>
      <span>last updated &middot; {last_date}</span>
    </div>
    <h1 class="main-title">trending<br><em>tech</em></h1>
  </div>
  {year_sections}
</main>
<script>
function showYear(y) {{
  document.querySelectorAll('.year-section').forEach(function(s) {{ s.style.display = 'none'; }});
  document.querySelectorAll('.year-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById('year-' + y).style.display = 'block';
  document.querySelector('[data-year="' + y + '"]').classList.add('active');
}}
if ('{first_year}') showYear('{first_year}');
</script>
</body>
</html>"""
