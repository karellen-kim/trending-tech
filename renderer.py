from collections import defaultdict

_FAVICON = """<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='5' fill='%231a1714'/%3E%3Cpolyline points='3,26 10,18 17,22 24,10 29,6' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpolyline points='22,5 29,6 28,13' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='5' fill='%231a1714'/%3E%3Cpolyline points='3,26 10,18 17,22 24,10 29,6' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpolyline points='22,5 29,6 28,13' fill='none' stroke='%23e05c1a' stroke-width='2.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">"""

_FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@400;600;700&display=swap" rel="stylesheet">"""

_BASE_CSS = """<style>
  :root {
    /* 에디토리얼 팔레트 — 딥그린 헤더 · 골드 악센트 · 크림 구분 띠 */
    --paper: #fffdf8; --paper-deep: #f6f1e2;
    --ink: #16211d; --ink-soft: #57544a; --ink-faint: #9a917d;
    --rule: #e6dfcd; --rule-strong: #ded6c2;
    --green: #1f3b34; --green-soft: #8fb3a6; --green-mute: #6f9789;
    --cream: #f7f4e9;
    /* 기존 규칙이 쓰던 이름을 새 색으로 잇는다 */
    --accent: #e8c46a; --accent-deep: #b08a2a; --accent-wash: #ece5d3;
    --serif: "Noto Serif KR", Georgia, serif;
    --sans: "Noto Sans KR", -apple-system, sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 15px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
</style>"""

_DAILY_CSS = """<style>
  body { max-width: 720px; margin: 0 auto; padding: 0 0 4rem; background: var(--paper); }
  /* 띠는 화면 폭까지, 글은 안쪽 여백 안에 — 래퍼 없이 요소마다 여백을 준다 */
  .page-meta, h1, .take, .highlight-list li, .item-head, .item-body,
  .item details > summary, .days-section-title, .day-link { padding-left: 1.15rem; padding-right: 1.15rem; }

  /* ── 상단 바 ── */
  .top-bar { display: flex; align-items: center; justify-content: space-between;
    background: var(--green); padding: 1rem 1.15rem 0.2rem; margin-bottom: 0; }
  .top-bar > span { color: var(--green-mute) !important; }
  .back-btn { font-family: var(--mono); font-size: 0.7rem; font-weight: 500; color: var(--green-soft);
    text-decoration: none; border: none; padding: 0; }
  .back-btn:hover { border-color: var(--green); color: var(--green); }

  /* ── 페이지 제목 ── */
  .page-meta { font-family: var(--mono); font-size: 0.63rem; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--green-soft); background: var(--green); padding-top: 1.3rem; padding-bottom: 0.5rem; margin-bottom: 0; }
  h1 { font-family: var(--serif); font-size: clamp(1.9rem, 5vw, 2.8rem); font-weight: 700;
    letter-spacing: -0.045em; line-height: 1.02; margin-bottom: 0; color: var(--cream);
    background: var(--green); padding-bottom: 1.5rem; text-wrap: pretty; }
  h1 em { font-style: normal; color: var(--accent); }

  /* ── 섹션 네비게이션 (sticky) ── */
  .page-nav { position: sticky; top: 0; background: var(--accent-wash); border-bottom: 1px solid var(--green);
    padding: 0.7rem 1.15rem; margin-bottom: 0; z-index: 20; display: flex; gap: 0.45rem;
    overflow-x: auto; scrollbar-width: none; }
  .page-nav::-webkit-scrollbar { height: 0; }
  .nav-link { font-size: 0.71rem; font-weight: 500; color: #3f4b42; text-decoration: none;
    padding: 0.35rem 0.75rem; border: 1px solid #cfc5ac; border-radius: 999px; background: var(--paper);
    white-space: nowrap; transition: all 0.12s; }
  .nav-link:hover { color: var(--green); background: var(--accent-wash); }
  .nav-link:hover { border-color: var(--green); }

  /* ── 섹션 ── */
  .section { margin-bottom: 0; scroll-margin-top: 48px; }

  /* ── 섹션 헤더 ── */
  .section-header { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 0; padding: 0.8rem 1rem; background: var(--green); }
  .section-icon { font-family: var(--mono); font-size: 0.6rem; font-weight: 600; color: var(--accent); letter-spacing: 0.16em; text-transform: uppercase; flex-shrink: 0; }
  .section-title { font-family: var(--serif); font-size: 0.98rem; font-weight: 600; color: var(--cream); }
  .section-count { font-family: var(--mono); font-size: 0.63rem; color: var(--green-soft); margin-left: auto; letter-spacing: 0.06em; white-space: nowrap; }

  /* ── 하이라이트 섹션 ── */
  .highlight-section .section-header { background: var(--accent-wash); border-top: 1px solid var(--green); border-bottom: 1px solid var(--green); }
  .highlight-section .section-icon { color: var(--accent-deep); }
  .highlight-section .section-title { color: var(--green); font-family: var(--sans); font-size: 0.82rem; font-weight: 700; letter-spacing: 0.02em; }
  .highlight-list { list-style: none; padding: 0; background: var(--paper); border-bottom: 1px solid var(--rule); }
  .highlight-list li { font-family: var(--serif); font-size: 0.95rem; font-weight: 600; color: var(--ink); padding: 0.85rem 1rem 0.85rem 2.1rem; position: relative; border-bottom: 1px solid var(--rule); line-height: 1.45; letter-spacing: -0.015em; }
  .highlight-list li:last-child { border-bottom: none; }
  .highlight-list li::before { content: ""; position: absolute; left: 1rem; top: 1.15rem; width: 7px; height: 7px; border-radius: 4px; background: var(--accent); }
  .highlight-list li a { color: inherit; text-decoration: none; }
  .highlight-list li a:hover { color: var(--accent-deep); text-decoration: underline; }

  /* ── 오늘의 해석 ── */
  .take { background: var(--paper); border-bottom: 1px solid var(--rule); padding: 1.4rem 1rem 1.6rem; }
  .take-headline { font-family: var(--serif); font-size: 1.12rem; font-weight: 700; line-height: 1.5;
    letter-spacing: -0.02em; color: var(--ink); text-wrap: pretty; }
  .take-body { margin-top: 0.85rem; font-size: 0.87rem; line-height: 1.75; color: var(--ink-soft); text-wrap: pretty; }
  .take-refs { margin-top: 1.1rem; padding-top: 0.9rem; border-top: 1px dashed var(--rule-strong);
    font-size: 0.79rem; line-height: 1.85; color: var(--ink-faint); }
  .take-refs span { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.1em;
    text-transform: uppercase; margin-right: 0.6rem; }
  .take-refs a { color: var(--ink-soft); text-decoration: none; border-bottom: 1px solid var(--rule); }
  .take-refs a:hover { text-decoration: underline; }

  /* ── 기간 해석의 핵심 문서 ── */
  .picks { margin-top: 1.1rem; padding-top: 0.9rem; border-top: 1px dashed var(--rule-strong); }
  .picks-label { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-faint); }
  .picks ol { margin: 0.6rem 0 0; padding-left: 1.2rem; }
  .picks li { font-size: 0.88rem; line-height: 1.6; margin-bottom: 0.5rem; }
  .picks li a { font-family: var(--serif); color: var(--ink); text-decoration: none; font-weight: 600; }
  .picks li a:hover { text-decoration: underline; }
  .pick-why { display: block; font-size: 0.76rem; color: var(--ink-faint); margin-top: 0.3rem;
    padding-left: 0.65rem; border-left: 2px solid var(--accent); }

  /* ── 꼭 봐야 할 글 ── */
  .item-star { color: var(--accent-deep); margin-right: 0.35rem; font-size: 0.8rem; }
  .item.important .item-name a { color: var(--green); }

  /* ── 오디오 리뷰 ── */
  .audio-block { display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;
    margin: 0 1rem 1.4rem; padding: 0.85rem 1rem; border-radius: 12px; background: var(--accent-wash); }
  .audio-label { font-family: var(--mono); font-size: 0.65rem; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--ink-faint); white-space: nowrap; }
  .audio-block a { font-size: 0.82rem; color: var(--green); text-decoration: none; font-weight: 500; }
  .audio-block a:hover { text-decoration: underline; }

  /* ── 아이템 (아코디언) ── */
  .item { border-bottom: 1px solid var(--rule); }
  .item:last-child { border-bottom: none; }
  .item details > summary { display: grid; grid-template-columns: 1fr auto auto; gap: 0.8rem;
    align-items: baseline; padding: 1rem 0; cursor: pointer; list-style: none; }
  .item details > summary::-webkit-details-marker { display: none; }
  .item details > summary:hover .item-name { color: var(--accent-deep); }
  .item-head { padding: 1rem 0; }
  .item-name { font-family: var(--serif); font-weight: 600; font-size: 1rem; line-height: 1.42;
    letter-spacing: -0.015em; color: var(--ink); min-width: 0; text-wrap: pretty; }
  .item-name a { color: var(--ink); text-decoration: none; }
  .item-name a:hover { color: var(--green); }
  .item-meta { font-family: var(--mono); font-size: 0.65rem; color: var(--ink-faint);
    letter-spacing: 0.08em; white-space: nowrap; }
  .item-toggle::before { content: "+"; font-family: var(--mono); font-size: 0.9rem; color: var(--ink-faint); }
  .item details[open] > summary .item-toggle::before { content: "\2212"; color: var(--accent); }
  .item-body { padding: 0 0 1.2rem; }
  .item-summary { font-size: 0.845rem; color: var(--ink-soft); line-height: 1.68; text-wrap: pretty; }
  .item-diagram { margin: 0 0 1rem; overflow-x: auto; }
  .item-diagram .diagram { margin: 0; padding: 1rem 0.9rem 0.7rem; border-radius: 10px; color: var(--ink);
    background: repeating-linear-gradient(135deg, #f4efe1 0 6px, var(--paper) 6px 12px);
    border: 1px dashed #d3c9b1; }
  /* svg 자체가 style="width:Npx;max-width:100%" 를 들고 있다 — 확대하지 않고 1:1 로 그린다 */
  .item-diagram svg { height: auto; display: block; margin: 0 auto; }
  .item-diagram figcaption { margin-top: 0.6rem; padding-top: 0.5rem; border-top: 1px solid var(--rule-strong);
    font-family: var(--serif); font-style: italic; font-size: 0.74rem; color: #7d7364; text-align: center; }
  .item-link { margin-top: 0.9rem; font-family: var(--mono); font-size: 0.7rem; }
  .item-link a { color: var(--green); text-decoration: none; border-bottom: 1px solid var(--accent); padding-bottom: 2px; }

  /* 긴 제목·URL 이 줄바꿈되지 않으면 가로 스크롤이 생긴다 */
  .item-name, .take-refs, .take-headline, .picks, .section-title { overflow-wrap: anywhere; }

  @media (max-width: 600px) {
    /* 띠는 화면 끝까지 닿아야 하므로 body 에 좌우 여백을 주지 않는다 */
    body { padding-bottom: 3rem; }
    .nav-link { font-size: 0.68rem; padding: 0.32rem 0.66rem; }
    h1 { font-size: 1.85rem; }
  }
</style>"""

_INDEX_CSS = """<style>
  body { max-width: 720px; margin: 0 auto; background: var(--paper); }

  /* ── 딥그린 표지 ── */
  .idx-head { background: var(--green); color: var(--cream); padding: 2rem 1.6rem 1.6rem; }
  .idx-kicker { display: flex; align-items: center; gap: 0.5rem; font-family: var(--mono);
    font-size: 0.66rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--green-soft); }
  .idx-kicker span { width: 18px; height: 1px; background: var(--green-soft); }
  .idx-title { font-family: var(--serif); font-size: clamp(2.6rem,11vw,3.4rem); font-weight: 700;
    line-height: 1; letter-spacing: -0.04em; margin-top: 0.85rem; color: var(--cream); }
  .idx-title em { font-style: normal; font-weight: 400; color: var(--accent); }
  .idx-foot { margin-top: 1.25rem; padding-top: 0.9rem; border-top: 1px solid rgba(242,239,228,0.22);
    display: flex; justify-content: space-between; align-items: baseline; }
  .idx-updated { font-family: var(--mono); font-size: 0.7rem; color: #a9c6bb; }
  .idx-year { font-family: var(--serif); font-size: 1.25rem; font-weight: 700; letter-spacing: 0.02em; color: var(--accent); }

  /* ── 월 구분 띠 ── */
  .m-band { display: flex; align-items: flex-end; justify-content: space-between;
    padding: 1rem 1.6rem 0.9rem; background: var(--accent-wash);
    border-top: 1px solid var(--green); border-bottom: 1px solid var(--green); }
  .m-band-l { display: flex; align-items: flex-end; gap: 0.62rem; }
  .m-num { font-family: var(--serif); font-size: 2.5rem; font-weight: 700; line-height: 0.8;
    letter-spacing: -0.04em; color: var(--green); }
  .m-names { display: flex; flex-direction: column; gap: 2px; }
  .m-ko { font-family: var(--serif); font-size: 0.94rem; font-weight: 600; line-height: 1; color: var(--green); }
  .m-en { font-family: var(--mono); font-size: 0.63rem; letter-spacing: 0.14em; text-transform: uppercase; color: #7d8b7f; }
  .m-count { font-family: var(--mono); font-size: 0.66rem; color: #7d8b7f; white-space: nowrap; }

  /* ── 이 달의 해석 ── */
  .m-take { display: block; padding: 1.15rem 1.6rem 1.25rem; border-bottom: 1px solid var(--rule);
    text-decoration: none; background: var(--paper); }
  .m-take:hover { background: var(--paper-deep); }
  .m-take-label { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.14em;
    text-transform: uppercase; color: var(--accent-deep); }
  .m-take-headline { margin-top: 0.5rem; font-family: var(--serif); font-size: 1rem; font-weight: 700;
    line-height: 1.5; letter-spacing: -0.02em; color: var(--ink); text-wrap: pretty; }
  .m-take-body { margin-top: 0.6rem; padding-left: 0.7rem; border-left: 2px solid var(--accent);
    font-size: 0.79rem; line-height: 1.6; color: var(--ink-soft); text-wrap: pretty; }
  .m-take-more { display: inline-block; margin-top: 0.8rem; font-family: var(--mono);
    font-size: 0.68rem; color: var(--green); }

  /* ── 주차 목록 ── */
  .note { display: flex; gap: 0.9rem; padding: 1.15rem 1.6rem; border-bottom: 1px solid var(--rule);
    text-decoration: none; color: var(--ink); }
  .note:hover { background: var(--paper-deep); }
  .note-rail { display: flex; flex-direction: column; align-items: center; gap: 6px; padding-top: 7px; }
  .note-dot { width: 7px; height: 7px; border-radius: 4px; background: var(--accent); }
  .note-line { flex: 1; width: 1px; background: var(--rule-strong); }
  .note-body { flex: 1; min-width: 0; }
  .note-top { display: flex; align-items: baseline; gap: 0.5rem; margin-bottom: 0.45rem; }
  .note-range { font-family: var(--mono); font-size: 0.72rem; font-weight: 500; color: var(--green); }
  .note-ago { margin-left: auto; font-family: var(--mono); font-size: 0.66rem; color: #b8ac98; white-space: nowrap; }
  .note-a { font-family: var(--serif); font-size: 1rem; font-weight: 600; line-height: 1.42;
    letter-spacing: -0.015em; color: var(--ink); text-wrap: pretty; }
  .note-b { margin-top: 0.5rem; padding-left: 0.7rem; border-left: 2px solid var(--accent);
    font-size: 0.78rem; line-height: 1.5; color: #6d675c; text-wrap: pretty; }

  .idx-tail { height: 2.5rem; }

  @media (prefers-reduced-motion: no-preference) {
    .note { animation: rise 0.5s cubic-bezier(0.22,1,0.36,1) both; }
    @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  }
</style>"""

_MONTH_NAMES = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}

def _e(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _item_html(name: str, url: str, meta: str, summary: str,
               name_ko: str = "", svg: str = "", important: bool = False) -> str:
    display_name = name_ko if name_ko and name_ko.strip() else name
    star = '<span class="item-star" title="꼭 봐야 할 글">★</span>' if important else ""
    link_html = f'<a href="{url}" target="_blank" rel="noopener">{_e(display_name)}</a>'
    has_body = bool((summary or "").strip()) or bool((svg or "").strip())
    cls = "item important" if important else "item"

    if not has_body:
        return f"""<div class="{cls}">
  <div class="item-head">
    <div class="item-name">{star}{link_html}</div>
    <div class="item-meta">{_e(meta)}</div>
  </div>
</div>"""

    body = ""
    if svg and svg.strip():
        body += f'<div class="item-diagram">{svg}</div>'
    if summary and summary.strip():
        body += f'<div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>'

    # 제목을 <summary> 안에서 링크로 두면 클릭이 펼침과 충돌하므로,
    # 접힌 헤더에는 텍스트만 두고 펼친 본문 하단에 원문 링크를 둔다.
    return f"""<div class="{cls}">
  <details>
    <summary>
      <span class="item-name">{star}{_e(display_name)}</span>
      <span class="item-meta">{_e(meta)}</span>
      <span class="item-toggle" aria-hidden="true"></span>
    </summary>
    <div class="item-body">
      {body}
      <div class="item-link">{link_html} &rarr;</div>
    </div>
  </details>
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

    audio = ""
    if data.get("audio_url"):
        audio = (f'<div class="audio-block">'
                 f'<span class="audio-label">오디오 리뷰</span>'
                 f'<a href="{data["audio_url"]}" target="_blank" rel="noopener">'
                 f'Gemini Notebook에서 듣기 &rarr;</a></div>')

    take = data.get("today_take") or {}
    if take.get("headline"):
        # 해석은 항목 나열이 아니라 오늘 글들을 관통하는 흐름 한 문장이다
        refs = ""
        if take.get("refs"):
            links_html = " · ".join(
                f'<a href="{r["url"]}" target="_blank" rel="noopener">{_e(r["text"])}</a>'
                if r.get("url") else _e(r["text"]) for r in take["refs"])
            refs = f'<div class="take-refs"><span>근거</span>{links_html}</div>'
        body_html = f'<p class="take-body">{_e(take["body"])}</p>' if take.get("body") else ""
        sections += _section_html("highlights", "★", "오늘의 해석",
            f'<div class="take"><p class="take-headline">{_e(take["headline"])}</p>'
            f'{body_html}{refs}</div>{audio}')
    elif highlights:
        links = data.get("highlight_links") or []
        rows = ""
        for n, h in enumerate(highlights):
            url = links[n].get("url", "") if n < len(links) else ""
            body = (f'<a href="{url}" target="_blank" rel="noopener">{_e(h)}</a>'
                    if url else _e(h))
            rows += f'<li>{body}</li>'
        sections += _section_html("highlights", "★", "오늘의 하이라이트",
            f'<ul class="highlight-list">{rows}</ul>{audio}')

    if company_blogs:
        sections += _section_html("tech-blog", "TECH", "기술 블로그", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""),
                       i.get("title_ko",""), i.get("svg",""), i.get("important", False))
            for i in company_blogs), len(company_blogs))

    if dev_blogs:
        sections += _section_html("dev-blogs", "DEV", "개발자 블로그 &amp; SNS", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""),
                       i.get("title_ko",""), i.get("svg",""), i.get("important", False))
            for i in dev_blogs), len(dev_blogs))

    if papers:
        sections += _section_html("papers", "PAPER", "AI / LLM 논문", "".join(
            _item_html(i["title"], i["url"], "arXiv", i.get("summary") or i.get("abstract",""),
                       i.get("title_ko",""), i.get("svg",""), i.get("important", False))
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
            _item_html(i["name"], i["url"], i.get("stars_today",""),
                       i.get("summary") or i.get("description",""), i.get("title_ko",""),
                       "", i.get("important", False))
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

_DAY_LINK_CSS = """<style>
  .days-section { margin-top: 0; }
  .days-section-title { font-size: 0.82rem; font-weight: 700; letter-spacing: 0.02em; color: var(--green);
    background: var(--accent-wash); border-top: 1px solid var(--green); border-bottom: 1px solid var(--green);
    padding: 0.8rem 1.15rem; margin-bottom: 0.9rem; text-transform: none; }
  .day-link { display: flex; align-items: center; gap: 0.9rem; margin: 0 1.15rem 0.6rem;
    padding: 0.85rem 1rem; border: 1px solid var(--rule-strong); border-radius: 14px;
    background: var(--paper); text-decoration: none; color: var(--ink); transition: all 0.12s; }
  .day-link:hover { border-color: var(--green); background: var(--paper-deep); }
  .day-label { font-family: var(--serif); font-weight: 600; font-size: 0.9rem; min-width: 3.4rem; color: var(--ink); }
  .day-date { font-family: var(--mono); font-size: 0.68rem; color: var(--ink-faint); }
  .day-arrow { font-family: var(--mono); font-size: 0.8rem; color: var(--accent-deep); margin-left: auto; }
</style>"""

def _period_take_html(take: dict | None, title: str) -> str:
    """주간·월간 해석 섹션. 해석 한 문장 + 근거 + 대표 문서 목록."""
    take = take or {}
    if not take.get("headline"):
        return ""
    body = f'<p class="take-body">{_e(take["body"])}</p>' if take.get("body") else ""
    picks = ""
    if take.get("picks"):
        rows = "".join(
            f'<li><a href="{p["url"]}" target="_blank" rel="noopener">{_e(p.get("text",""))}</a>'
            + (f'<span class="pick-why">{_e(p["why"])}</span>' if p.get("why") else "")
            + "</li>"
            for p in take["picks"] if p.get("url"))
        if rows:
            picks = f'<div class="picks"><span class="picks-label">핵심 문서</span><ol>{rows}</ol></div>'
    return f"""<div class="section highlight-section" id="take">
  <div class="section-header">
    <span class="section-icon">★</span>
    <span class="section-title">{title}</span>
  </div>
  <div class="take"><p class="take-headline">{_e(take["headline"])}</p>{body}{picks}</div>
</div>"""


def render_weekly_page(week_data: dict) -> str:
    """
    week_data: {
      "week_id": "2026-W22",
      "week_label": "2026년 5월 25일 ~ 5월 31일",
      "highlights": [...],          # 일요일에만 채워짐
      "days": [{"date":"2026-05-27", "label":"화요일", "url":"2026-05-27.html"}, ...]
    }
    """
    week_id = week_data["week_id"]
    label = week_data.get("week_label", week_id)
    highlights = week_data.get("highlights", [])
    days = week_data.get("days", [])

    take_html = _period_take_html(week_data.get("week_take"), "이 주의 해석")

    hl_html = ""
    if highlights:
        # 예전 주간 페이지에는 문장만 남아 있어 링크를 걸 수 없다
        rows = "".join(
            (f'<li><a href="{h["url"]}" target="_blank" rel="noopener">{_e(h.get("text",""))}</a></li>'
             if isinstance(h, dict) and h.get("url")
             else f'<li>{_e(h.get("text","") if isinstance(h, dict) else h)}</li>')
            for h in highlights)
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
{_DAY_LINK_CSS}
</head>
<body>
<div class="top-bar">
  <a href="./index.html" class="back-btn">&larr; index</a>
  <span style="font-family:var(--mono);font-size:0.65rem;color:var(--ink-faint);letter-spacing:0.1em">TRENDING-TECH</span>
</div>
<div class="page-meta">{week_id}</div>
<h1>{label.split("(")[0].strip()}</h1>
{take_html}
{hl_html}
<div class="days-section">
  <div class="days-section-title">이번 주 일별 보기</div>
  {days_html}
</div>
</body>
</html>"""

def render_index_page(entries: list[dict], month_takes: dict | None = None) -> str:
    """month_takes: {"2026-07": {"headline":..., "body":...}} — 월 페이지의 해석을
    목록에서도 보여준다. 렌더러가 파일을 읽지 않도록 호출부에서 넘긴다."""
    from datetime import date as _date, datetime

    def _week_id(d: str) -> str:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"

    def _week_range(week_id: str) -> tuple:
        y, w = week_id.split("-W")
        return (datetime.strptime(f"{y}-W{w}-1", "%G-W%V-%u").date(),
                datetime.strptime(f"{y}-W{w}-7", "%G-W%V-%u").date())

    # 연도 → 월 → 주차
    by_month = defaultdict(lambda: defaultdict(list))
    for e in sorted(entries, key=lambda x: x["date"], reverse=True):
        mid = e["date"][:7]
        by_month[mid][_week_id(e["date"])].append(e)

    all_dates = sorted(e["date"] for e in entries)
    last_date = all_dates[-1] if all_dates else "—"
    newest = _date.fromisoformat(last_date) if all_dates else None
    year = last_date[:4] if all_dates else ""

    body = ""
    for mid in sorted(by_month.keys(), reverse=True):
        y, mo = mid.split("-")
        wids = sorted(by_month[mid].keys(), reverse=True)
        days = sum(len(v) for v in by_month[mid].values())
        body += f"""<div class="m-band">
  <div class="m-band-l">
    <span class="m-num">{mo}</span>
    <div class="m-names"><span class="m-ko">{int(mo)}월</span><span class="m-en">{_MONTH_NAMES[mo]}</span></div>
  </div>
  <span class="m-count">{days}일 · {len(wids)}주</span>
</div>"""

        mt = (month_takes or {}).get(mid) or {}
        if mt.get("headline"):
            mt_body = f'<p class="m-take-body">{_e(mt["body"])}</p>' if mt.get("body") else ""
            body += (f'<a class="m-take" href="./{mid}.html">'
                     f'<span class="m-take-label">이 달의 해석</span>'
                     f'<p class="m-take-headline">{_e(mt["headline"])}</p>'
                     f'{mt_body}<span class="m-take-more">월간 페이지 &rarr;</span></a>')

        for wid in wids:
            week_entries = sorted(by_month[mid][wid], key=lambda x: x["date"])
            s_, e_ = _week_range(wid)
            if s_.month == e_.month:
                label = f"{s_.month}월 {s_.day}일~{e_.day}일"
            else:
                label = f"{s_.month}월 {s_.day}일~{e_.month}월 {e_.day}일"

            # 그 주 마지막 수록일이 얼마나 지났는지 — Wxx 대신 시간 감각을 준다
            ago = ""
            if newest:
                gap = (newest - _date.fromisoformat(week_entries[-1]["date"])).days
                ago = "오늘" if gap <= 0 else f"{gap}일 전"

            hl = []
            for we in week_entries:
                hl.extend(h for h in (we.get("highlights") or []) if h)
            a = _e(hl[0]) if hl else f"{len(week_entries)}일치 기록"
            b = f'<div class="note-b">{_e(hl[1])}</div>' if len(hl) > 1 else ""

            body += f"""<a class="note" href="./{wid}.html">
  <div class="note-rail"><span class="note-dot"></span><span class="note-line"></span></div>
  <div class="note-body">
    <div class="note-top"><span class="note-range">{label}</span><span class="note-ago">{ago}</span></div>
    <div class="note-a">{a}</div>
    {b}
  </div>
</a>"""

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
<header class="idx-head">
  <div class="idx-kicker"><span></span>weekly archive</div>
  <h1 class="idx-title">trending<br><em>tech</em></h1>
  <div class="idx-foot">
    <span class="idx-updated">last updated {last_date}</span>
    <span class="idx-year">{year}</span>
  </div>
</header>
{body}
<div class="idx-tail"></div>
</body>
</html>"""


def render_monthly_page(month_data: dict) -> str:
    """월간 페이지. 이 달의 해석 + 대표 문서 + 그 달의 주간 링크 목록."""
    mid = month_data["month_id"]
    label = month_data.get("month_label", mid)
    take_html = _period_take_html(month_data.get("month_take"), "이 달의 해석")

    weeks_html = ""
    for w in month_data.get("weeks", []):
        weeks_html += (f'<a href="./{w["url"]}" class="day-link">'
                       f'<span class="day-label">{_e(w["label"])}</span>'
                       f'<span class="day-date">{_e(w.get("range",""))}</span>'
                       f'<span class="day-arrow">&rarr;</span></a>')

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{label} — Trending Tech</title>
{_FAVICON}
{_FONTS}
{_BASE_CSS}
{_DAILY_CSS}
{_DAY_LINK_CSS}
</head>
<body>
<div class="top-bar">
  <a href="./index.html" class="back-btn">&larr; 목록</a>
  <span class="page-meta">{mid}</span>
</div>
<div class="page-meta">MONTHLY DIGEST</div>
<h1>{label} <em>기술 흐름</em></h1>
{take_html}
<div class="section" id="weeks">
  <div class="section-header">
    <span class="section-icon">주간</span>
    <span class="section-title">이 달의 주차</span>
  </div>
  {weeks_html}
</div>
</body>
</html>"""
