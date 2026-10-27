from unittest.mock import patch
import main


import pytest


@pytest.fixture(autouse=True)
def isolated_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DOCS_DIR", tmp_path)


def test_collect_separates_ranked_hn_and_caps_reddit(monkeypatch):
    hn = [{"title": f"h{i}", "url": f"http://h{i}", "rank": i + 1} for i in range(4)]
    rd = [{"title": f"r{i}", "url": f"http://r{i}"} for i in range(7)]
    rd.insert(2, {"title": "r1 duplicate", "url": "http://r1"})
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", return_value=hn) as fetch_hn, \
         patch("main.fetch_all_reddit", return_value=rd), \
         patch("main.filter_important_papers", return_value=[]), \
         patch("main._load_recent_urls", return_value={"http://h0", "http://r0"}):
        data = main.collect("2026-10-27")
    fetch_hn.assert_called_once_with(day="2026-10-26")
    assert [i["title"] for i in data["hn"]] == ["h0", "h1", "h2"]
    assert [i["title"] for i in data["reddit"]] == ["r1", "r2", "r3", "r4", "r5"]
    assert data["hn_date"] == "2026-10-26"
    assert "community" not in data


def test_collect_explicit_hn_day_and_failure():
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", side_effect=RuntimeError("HN503")) as fetch_hn, \
         patch("main.fetch_all_reddit", return_value=[{"title": "r0", "url": "http://r0"}]), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-10-26", hn_day="2026-10-26")
    fetch_hn.assert_called_once_with(day="2026-10-26")
    assert data["hn"] == []
    assert len(data["reddit"]) == 1
    assert data["hn_date"] == "2026-10-26"


def test_analyze_items_drops_non_today(monkeypatch):
    def fake(title, content, pub_hint, today, date_verified=False):
        return {"is_today": pub_hint == "today", "pub_date": pub_hint,
                "title_ko": "한글", "summary": "요약"}

    monkeypatch.setattr(main, "analyze_item", fake)
    items = [
        {"title": "a", "summary": "가" * 300, "pub_hint": "today"},
        {"title": "b", "summary": "가" * 300, "pub_hint": "2026-01-01"},
    ]
    out = main._analyze_items(items, "summary")
    assert len(out) == 1 and out[0]["title"] == "a"
    assert out[0]["title_ko"] == "한글"


def test_analyze_items_keeps_all_when_filter_off(monkeypatch):
    monkeypatch.setattr(main, "analyze_item", lambda *a, **kw: {
        "is_today": False, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": "p", "abstract": "가" * 300}]
    out = main._analyze_items(items, "abstract", filter_today=False)
    assert len(out) == 1


def test_analyze_items_honors_configured_parallelism(monkeypatch):
    import time
    monkeypatch.setattr(main, "SUMMARY_WORKERS", 4)
    monkeypatch.setattr(main, "analyze_item", lambda *a, **kw: time.sleep(0.2) or {
        "is_today": True, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": f"t{i}", "summary": "가" * 300, "pub_hint": "x"} for i in range(8)]
    t0 = time.monotonic()
    main._analyze_items(items, "summary")
    assert time.monotonic() - t0 < 1.0


def test_analyze_items_calls_llm_once_per_item(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "analyze_item",
                        lambda t, c, p, d, **kw: calls.append(t) or {
                            "is_today": True, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": f"t{i}", "summary": "가" * 300, "pub_hint": "x"} for i in range(5)]
    main._analyze_items(items, "summary")
    assert len(calls) == 5, "항목당 호출은 정확히 1회여야 한다"

def test_summarize_translates_community(monkeypatch):
    """커뮤니티 항목도 제목 번역·요약을 거친다. 날짜 판정은 하지 않는다."""
    got = {}
    monkeypatch.setattr(main, "analyze_item",
                        lambda t, c, p, d, date_verified=False: got.update(
                            title=t, verified=date_verified) or {
                            "is_today": False, "pub_date": "x",
                            "title_ko": "한글제목", "summary": "요약"})
    monkeypatch.setattr(main, "generate_today_take", lambda d: {})
    monkeypatch.setattr(main, "generate_highlight_links", lambda d: [])
    monkeypatch.setattr(main, "generate_highlights", lambda d: [])
    data = main.summarize({"date": "2026-09-20", "company_blogs": [], "dev_blogs": [],
                           "papers": [], "github": [],
                           "community": [{"title": "Jev is not an LLM", "url": "http://a"}]})
    assert data["community"][0]["title_ko"] == "한글제목"
    assert got["verified"] is True, "날짜 판정을 태우면 요약이 빈 값이 된다"


# ── Gemini Notebook 오디오 오버뷰 단계 ──

def test_audio_step_skipped_when_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", False)
    monkeypatch.setattr(main, "generate_audio_review", lambda *a, **kw: called.append(1))
    assert main.make_audio({"date": "2026-08-14",
                            "highlight_links": [{"url": "http://a"}]}) == ""
    assert called == []


def test_audio_step_passes_highlight_urls(monkeypatch):
    got = {}
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", True)
    monkeypatch.setattr(main, "generate_audio_review",
                        lambda urls, title="", date_str="": got.update(
                            urls=urls, title=title, date_str=date_str) or "http://nb/1")
    data = {"date": "2026-08-14",
            "today_take": {"headline": "실행 계층으로 이동한다"},
            "highlight_links": [{"url": "http://a"}, {"url": "http://b"}, {"url": ""}]}
    assert main.make_audio(data) == "http://nb/1"
    assert got["urls"] == ["http://a", "http://b"]
    assert got["title"] == "실행 계층으로 이동한다"
    assert got["date_str"] == "26.08.14"


def test_audio_skipped_without_links(monkeypatch):
    called = []
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", True)
    monkeypatch.setattr(main, "generate_audio_review", lambda *a, **kw: called.append(1))
    assert main.make_audio({"date": "2026-08-14", "highlight_links": []}) == ""
    assert called == []


def test_audio_failure_does_not_break_pipeline(monkeypatch):
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", True)
    monkeypatch.setattr(main, "generate_audio_review",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert main.make_audio({"date": "2026-08-14",
                            "highlight_links": [{"url": "http://a"}]}) == ""


# ── 본문이 짧은 RSS 요약에 가려지는 문제 (Databricks·Toss 실측) ──

def test_analyze_picks_longest_content(monkeypatch):
    """RSS summary 가 86자여도 truthy 라 or 연산에서 본문 1999자를 가려버렸다"""
    got = {}
    monkeypatch.setattr(main, "analyze_item",
                        lambda t, c, p, d, date_verified=False: got.update(content=c) or {
                            "is_today": True, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": "t", "summary": "짧은 티저 " * 5, "content": "진짜 본문 " * 200,
              "pub_hint": "x", "date_verified": True}]
    main._analyze_items(items, "summary")
    assert "진짜 본문" in got["content"], "더 긴 쪽을 써야 한다"


def test_analyze_keeps_summary_when_no_content(monkeypatch):
    got = {}
    monkeypatch.setattr(main, "analyze_item",
                        lambda t, c, p, d, date_verified=False: got.update(content=c) or {
                            "is_today": True, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": "t", "summary": "본문이 여기 다 있다 " * 30,
              "pub_hint": "x", "date_verified": True}]
    main._analyze_items(items, "summary")
    assert "본문이 여기 다 있다" in got["content"]


def test_summarize_hn_and_reddit_uses_real_body_and_no_body_fallback(monkeypatch):
    calls = {}
    fetched = []

    def enrich(items):
        fetched.extend(item['url'] for item in items)
        for item in items:
            if item['title'] == 'Fetched':
                item['content'] = '본문 ' * 80
        return items

    def analyze(title, content, *args, **kwargs):
        calls[title] = (content, kwargs['date_verified'])
        return {'is_today': True, 'pub_date': '', 'title_ko': title + ' 번역',
                'summary': '원문 요약' if content else '지어낸 요약'}

    monkeypatch.setattr(main, 'enrich_with_body', enrich)
    monkeypatch.setattr(main, 'analyze_item', analyze)
    monkeypatch.setattr(main, 'generate_today_take', lambda data: {'headline': '흐름', 'refs': []})
    data = main.summarize({'date': '2026-10-27', 'company_blogs': [], 'dev_blogs': [],
                          'papers': [], 'github': [],
                          'hn': [{'title': 'Provided', 'url': 'https://provided', 'content': '기사 ' * 80},
                                 {'title': 'SummaryOnly', 'url': 'https://summary', 'summary': '제공 본문 ' * 80},
                                 {'title': 'Fetched', 'url': 'https://fetched'}],
                          'reddit': [{'title': 'Unavailable', 'url': 'https://unavailable'}]})
    assert fetched == ['https://fetched', 'https://unavailable']
    assert calls['Provided'] == ('기사 ' * 80, True)
    assert calls['SummaryOnly'] == ('제공 본문 ' * 80, True)
    assert calls['Fetched'] == ('본문 ' * 80, True)
    assert calls['Unavailable'] == ('', True)
    assert [item['summary'] for item in data['hn']] == ['원문 요약', '원문 요약', '원문 요약']
    assert data['reddit'][0]['summary'] == ''
    assert data['reddit'][0]['title_ko'] == 'Unavailable 번역'


def test_audio_reuses_existing_saved_notebook(monkeypatch, tmp_path):
    import json
    url = 'https://notebooklm.google.com/notebook/existing'
    (tmp_path / '2026-10-26.json').write_text(json.dumps({'audio_url': url}))
    monkeypatch.setattr(main, 'ENABLE_NOTEBOOKLM', True)
    with patch('main.generate_audio_review') as generate:
        assert main.make_audio({'date': '2026-10-26', 'highlight_links': [{'url': 'https://source'}]}) == url
    generate.assert_not_called()


def test_main_forwards_explicit_hn_day(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setenv('RUN_DATE', '2026-10-26')
    monkeypatch.setenv('DRY', '1')
    monkeypatch.setattr(main.signal, 'signal', Mock())
    monkeypatch.setattr(main.signal, 'alarm', Mock())
    collect = Mock(return_value={'date': '2026-10-26'})
    monkeypatch.setattr(main, 'collect', collect)
    monkeypatch.setattr(main, 'summarize', lambda data: data)
    monkeypatch.setattr(main, 'make_audio', lambda data: '')
    monkeypatch.setattr(main, 'save_html', lambda data: [])
    monkeypatch.setattr(main, 'save_weekly_page', lambda today: None)
    monkeypatch.setattr(main, 'save_monthly_page', lambda today: '')
    main.main(hn_day='2026-10-26')
    collect.assert_called_once_with('2026-10-26', hn_day='2026-10-26')
