from collections import defaultdict

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
  body { display: flex; min-height: 100vh; }
  .sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--rule); position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 2rem 0; }
  .sidebar-header { padding: 0 1.4rem 1.4rem; border-bottom: 1px solid var(--rule); margin-bottom: 1rem; }
  .s-label { font-size: 0.62rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; margin-bottom: 0.4rem; }
  .s-title { font-size: 1rem; font-weight: 700; color: var(--ink); letter-spacing: -0.02em; }
  .year-btn { width: 100%; padding: 0.7rem 1.4rem; display: block; cursor: pointer; background: none; border: none; font-family: var(--sans); text-align: left; font-size: 0.9rem; font-weight: 500; color: var(--ink-soft); border-left: 2px solid transparent; transition: all 0.12s; }
  .year-btn:hover { background: var(--paper-deep); }
  .year-btn.active { background: var(--accent-wash); border-left-color: var(--accent); color: var(--accent-deep); font-weight: 600; }
  .main { flex: 1; padding: 3rem 4rem; max-width: 800px; }
  .main-label { font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.5rem; }
  h1 { font-size: 2.8rem; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 2.5rem; }
  h1 em { font-style: normal; color: var(--accent); }
  .year-section { display: none; }
  .month-block { margin-bottom: 0.5rem; }
  .month-btn { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 0.8rem 0; background: none; border: none; border-bottom: 1px solid var(--rule); cursor: pointer; font-family: var(--sans); }
  .month-btn:hover .month-label { color: var(--accent-deep); }
  .month-label { font-size: 0.95rem; font-weight: 600; color: var(--ink); }
  .month-arrow { font-family: var(--mono); font-size: 0.8rem; color: var(--ink-faint); transition: transform 0.2s; }
  .month-btn.open .month-arrow { transform: rotate(90deg); color: var(--accent); }
  .month-highlights { padding: 0.6rem 0 0.4rem 0.5rem; }
  .month-highlights ul { list-style: none; padding: 0; }
  .month-highlights li { font-size: 0.85rem; color: var(--ink-soft); padding: 0.2rem 0 0.2rem 1rem; position: relative; }
  .month-highlights li::before { content: "·"; position: absolute; left: 0; color: var(--accent); }
  .month-dates { padding: 0.6rem 0; display: none; flex-wrap: wrap; gap: 0.4rem; }
  .date-link { font-family: var(--mono); font-size: 0.75rem; padding: 0.25rem 0.6rem; border: 1px solid var(--rule); color: var(--ink-soft); text-decoration: none; transition: all 0.12s; }
  .date-link:hover { border-color: var(--accent); color: var(--accent-deep); background: var(--accent-wash); }
</style>"""

_MONTH_NAMES = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}

def _e(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _item_html(name: str, url: str, meta: str, summary: str) -> str:
    return f"""<div class="item">
  <div class="item-left">
    <div class="item-name"><a href="{url}" target="_blank" rel="noopener">{_e(name)}</a></div>
    <div class="item-meta">{_e(meta)}</div>
    <div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>
  </div>
  <div class="item-arrow"><a href="{url}" target="_blank" rel="noopener">&rarr;</a></div>
</div>"""

_SECTIONS_META = [
    ("highlights",    "★",    "오늘의 하이라이트"),
    ("tech-blog",     "TECH", "기술 블로그"),
    ("dev-blogs",     "DEV",  "개발자 블로그 &amp; SNS"),
    ("papers",        "PAPER","AI / LLM 논문"),
    ("hn-reddit",     "COMM", "Hacker News &amp; Reddit"),
    ("github",        "CODE", "GitHub 트렌딩"),
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
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""))
            for i in company_blogs), len(company_blogs))

    if dev_blogs:
        sections += _section_html("dev-blogs", "DEV", "개발자 블로그 &amp; SNS", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""))
            for i in dev_blogs), len(dev_blogs))

    if papers:
        sections += _section_html("papers", "PAPER", "AI / LLM 논문", "".join(
            _item_html(i["title"], i["url"], "arXiv", i.get("summary", i.get("abstract","")))
            for i in papers), len(papers))

    if hn_reddit:
        sections += _section_html("hn-reddit", "COMM", "Hacker News &amp; Reddit", "".join(
            _item_html(
                i.get("title",""), i["url"],
                f"{i.get('source','HN')} · {i.get('points',0)} pts" if "points" in i else i.get("source",""),
                i.get("summary",""))
            for i in hn_reddit), len(hn_reddit))

    if github:
        sections += _section_html("github", "CODE", "GitHub 트렌딩", "".join(
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

def render_index_page(entries: list[dict]) -> str:
    by_year = defaultdict(lambda: defaultdict(list))
    for e in sorted(entries, key=lambda x: x["date"], reverse=True):
        y, m, _ = e["date"].split("-")
        by_year[y][m].append(e)

    years = sorted(by_year.keys(), reverse=True)
    sidebar = "".join(
        f'<button class="year-btn" data-year="{y}" onclick="showYear(\'{y}\')">{y}</button>'
        for y in years)

    year_sections = ""
    for y in years:
        months_html = ""
        for m in sorted(by_year[y].keys(), reverse=True):
            month_entries = by_year[y][m]
            highlights = []
            for e in month_entries:
                highlights.extend(e.get("highlights", [])[:2])
            hl_html = "".join(f"<li>{_e(h)}</li>" for h in highlights[:3])
            dates_html = "".join(
                f'<a href="./{e["date"]}.html" class="date-link">{e["date"]}</a>'
                for e in sorted(month_entries, key=lambda x: x["date"], reverse=True))
            months_html += f"""<div class="month-block">
  <button class="month-btn" onclick="toggleMonth(this)">
    <span class="month-label">{y}.{m} {_MONTH_NAMES[m]}</span>
    <span class="month-arrow">&rarr;</span>
  </button>
  <div class="month-highlights"><ul>{hl_html}</ul></div>
  <div class="month-dates">{dates_html}</div>
</div>"""
        year_sections += f'<div class="year-section" id="year-{y}">{months_html}</div>'

    first_year = years[0] if years else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trending Tech</title>
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
  <div class="main-label">TRENDING-TECH &middot; ARCHIVE</div>
  <h1>all <em>trends</em></h1>
  {year_sections}
</main>
<script>
function showYear(y) {{
  document.querySelectorAll('.year-section').forEach(function(s) {{ s.style.display = 'none'; }});
  document.querySelectorAll('.year-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById('year-' + y).style.display = 'block';
  document.querySelector('[data-year="' + y + '"]').classList.add('active');
}}
function toggleMonth(btn) {{
  btn.classList.toggle('open');
  var dates = btn.nextElementSibling.nextElementSibling;
  dates.style.display = dates.style.display === 'flex' ? 'none' : 'flex';
}}
if ('{first_year}') showYear('{first_year}');
</script>
</body>
</html>"""
