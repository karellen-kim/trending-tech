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
