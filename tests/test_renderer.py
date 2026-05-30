from renderer import render_daily_page, render_index_page

SAMPLE_DATA = {
    "date": "2026-05-31",
    "github": [{"name": "microsoft/phi-4", "url": "https://github.com/microsoft/phi-4",
                "description": "Small LM", "stars_today": "1,234 stars", "summary": "경량 모델입니다."}],
    "hn": [{"title": "LLaMA 4 Released", "url": "https://example.com",
            "points": 500, "comments": 200, "hn_url": "https://news.ycombinator.com/item?id=1",
            "summary": "오픈소스 LLM입니다."}],
    "papers": [{"title": "Paper A", "url": "https://arxiv.org/abs/1",
                "abstract": "...", "summary": "트랜스포머 개선입니다."}],
    "blogs": [{"title": "New Post", "url": "https://martinfowler.com/post",
               "source": "Martin Fowler", "summary": "패턴 글입니다."}],
}

def test_render_daily_page_is_html():
    html = render_daily_page(SAMPLE_DATA)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026-05-31" in html

def test_render_daily_page_has_sections():
    html = render_daily_page(SAMPLE_DATA)
    assert "GitHub Trending" in html
    assert "Hacker News" in html
    assert "AI / LLM Papers" in html
    assert "Developer Blogs" in html

def test_render_daily_page_has_items():
    html = render_daily_page(SAMPLE_DATA)
    assert "microsoft/phi-4" in html
    assert "LLaMA 4 Released" in html

def test_render_index_page_is_html():
    entries = [{"date": "2026-05-31", "highlights": ["LLaMA 4", "phi-4"]}]
    html = render_index_page(entries)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026" in html
    assert "2026-05-31" in html
