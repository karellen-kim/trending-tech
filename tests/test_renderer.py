from renderer import render_daily_page, render_index_page

SAMPLE_DATA = {
    "date": "2026-05-31",
    "highlights": ["LLaMA 4 공개로 오픈소스 LLM 경쟁 심화", "Cloudflare Workers AI 업데이트"],
    "github": [{"name": "microsoft/phi-4", "url": "https://github.com/microsoft/phi-4",
                "description": "Small LM", "stars_today": "1,234 stars", "summary": "경량 모델입니다."}],
    "hn": [{"title": "LLaMA 4 Released", "url": "https://example.com",
            "points": 500, "comments": 200, "hn_url": "https://news.ycombinator.com/item?id=1",
            "summary": "오픈소스 LLM입니다."}],
    "reddit": [{"title": "New tokenizer trick", "url": "https://reddit.com/r/ML/1",
                "source": "r/MachineLearning", "summary": "토크나이저 최적화입니다."}],
    "papers": [{"title": "Paper A", "url": "https://arxiv.org/abs/1",
                "abstract": "...", "summary": "트랜스포머 개선입니다."}],
    "company_blogs": [{"title": "Netflix new infra", "url": "https://netflixtechblog.com/1",
                       "source": "Netflix Tech Blog", "summary": "인프라 개선 사례입니다."}],
    "dev_blogs": [{"title": "New Post", "url": "https://martinfowler.com/post",
                   "source": "Martin Fowler", "summary": "패턴 글입니다."}],
}

def test_render_daily_page_is_html():
    html = render_daily_page(SAMPLE_DATA)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026-05-31" in html

def test_render_daily_page_has_sections():
    html = render_daily_page(SAMPLE_DATA)
    assert "GitHub 트렌딩" in html
    assert "Hacker News" in html
    assert "AI / LLM 논문" in html
    assert "개발자 블로그" in html
    assert "기술 블로그" in html
    assert "하이라이트" in html

def test_render_daily_page_section_order():
    html = render_daily_page(SAMPLE_DATA)
    positions = {
        "하이라이트": html.index("하이라이트"),
        "기술 블로그": html.index("기술 블로그"),
        "개발자 블로그": html.index("개발자 블로그"),
        "AI / LLM 논문": html.index("AI / LLM 논문"),
        "Hacker News": html.index("Hacker News"),
        "GitHub 트렌딩": html.index("GitHub 트렌딩"),
    }
    assert positions["하이라이트"] < positions["기술 블로그"]
    assert positions["기술 블로그"] < positions["개발자 블로그"]
    assert positions["개발자 블로그"] < positions["AI / LLM 논문"]
    assert positions["AI / LLM 논문"] < positions["Hacker News"]
    assert positions["Hacker News"] < positions["GitHub 트렌딩"]

def test_render_daily_page_has_items():
    html = render_daily_page(SAMPLE_DATA)
    assert "microsoft/phi-4" in html
    assert "LLaMA 4 Released" in html

def test_item_is_collapsible():
    from renderer import _item_html
    html = _item_html("Title", "http://x", "meta", "요약 본문", "한글제목")
    assert "<details" in html and "<summary" in html and "한글제목" in html


def test_collapsed_by_default():
    from renderer import _item_html
    assert "<details open" not in _item_html("T", "http://x", "m", "본문", "")


def test_svg_is_embedded_raw_not_escaped():
    from renderer import _item_html
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="5" height="5"/></svg>'
    html = _item_html("T", "http://x", "m", "본문", "", svg)
    assert "<svg" in html and "&lt;svg" not in html


def test_summary_is_still_escaped():
    from renderer import _item_html
    html = _item_html("T", "http://x", "m", "<script>alert(1)</script>", "")
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_item_without_summary_has_no_toggle():
    from renderer import _item_html
    assert "<details" not in _item_html("T", "http://x", "m", "", "")


def test_render_index_page_is_html():
    entries = [{"date": "2026-05-31", "highlights": ["LLaMA 4", "phi-4"]}]
    html = render_index_page(entries)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026" in html
    assert "2026-W22" in html  # 날짜 대신 주차 링크


# ── 해석 섹션 / 중요 표시 ──

TAKE_DATA = dict(SAMPLE_DATA, today_take={
    "headline": "경쟁력이 실행 계층으로 이동한다",
    "body": "여러 글이 같은 방향을 가리킨다.",
    "refs": [{"text": "글1", "url": "http://a", "source": "A"}],
})


def test_take_section_shows_headline_and_body():
    html = render_daily_page(TAKE_DATA)
    assert "오늘의 해석" in html
    assert "경쟁력이 실행 계층으로 이동한다" in html
    assert "여러 글이 같은 방향을 가리킨다." in html


def test_take_section_shows_evidence_links():
    html = render_daily_page(TAKE_DATA)
    assert 'href="http://a"' in html
    assert "근거" in html


def test_falls_back_to_list_without_take():
    """CSS 주석에도 같은 낱말이 있어 섹션 제목으로 정확히 확인한다"""
    html = render_daily_page(SAMPLE_DATA)
    assert '<span class="section-title">오늘의 하이라이트</span>' in html
    assert '<span class="section-title">오늘의 해석</span>' not in html
    assert 'class="take"' not in html


def test_take_replaces_highlight_list():
    html = render_daily_page(TAKE_DATA)
    assert '<span class="section-title">오늘의 해석</span>' in html
    assert '<span class="section-title">오늘의 하이라이트</span>' not in html


def test_important_item_gets_star():
    from renderer import _item_html
    html = _item_html("T", "http://x", "m", "요약", "", "", True)
    assert "item-star" in html and "★" in html
    assert 'class="item important"' in html


def test_normal_item_has_no_star():
    from renderer import _item_html
    html = _item_html("T", "http://x", "m", "요약", "", "", False)
    assert "item-star" not in html
    assert 'class="item"' in html


# ── 주간 페이지의 해석 섹션 ──

WEEK_DATA = {
    "week_id": "2026-W34", "week_label": "2026년 34주차 (8/17 – 8/23)",
    "days": [{"date": "2026-08-17", "label": "월요일", "url": "2026-08-17.html"}],
    "week_take": {
        "headline": "에이전트가 실행 계층으로 내려왔다",
        "body": "여러 날의 글이 같은 방향을 가리킨다.",
        "picks": [{"text": "핵심 문서", "url": "http://a", "why": "판을 바꾼 발표"}],
    },
}


def test_weekly_page_shows_take():
    from renderer import render_weekly_page
    html = render_weekly_page(WEEK_DATA)
    assert "이 주의 해석" in html
    assert "에이전트가 실행 계층으로 내려왔다" in html
    assert "여러 날의 글이 같은 방향을 가리킨다." in html


def test_weekly_page_shows_picks_with_links():
    from renderer import render_weekly_page
    html = render_weekly_page(WEEK_DATA)
    assert 'href="http://a"' in html
    assert "핵심 문서" in html
    assert "판을 바꾼 발표" in html


def test_weekly_page_without_take_still_renders():
    from renderer import render_weekly_page
    data = {k: v for k, v in WEEK_DATA.items() if k != "week_take"}
    html = render_weekly_page(data)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026-08-17.html" in html
