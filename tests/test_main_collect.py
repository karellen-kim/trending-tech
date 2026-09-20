from unittest.mock import patch
import main


def test_merge_community_interleaves_and_caps():
    """Reddit RSS 에는 점수가 없어 한 기준으로 정렬할 수 없다. 번갈아 섞는다."""
    hn = [{"title": f"h{i}"} for i in range(4)]
    rd = [{"title": f"r{i}"} for i in range(4)]
    out = main._merge_community(hn, rd, limit=5)
    assert [i["title"] for i in out] == ["h0", "r0", "h1", "r1", "h2"]


def test_merge_community_drops_duplicate_urls():
    """HN 과 r/programming 이 같은 글을 싣는다. 5칸짜리 섹션에서 두 칸을 먹으면 안 된다."""
    hn = [{"title": "a", "url": "http://x"}, {"title": "b", "url": "http://y"}]
    rd = [{"title": "a-dup", "url": "http://x"}, {"title": "c", "url": "http://z"}]
    out = main._merge_community(hn, rd, limit=5)
    assert [i["url"] for i in out] == ["http://x", "http://y", "http://z"]


def test_merge_community_fills_from_one_side():
    """한쪽이 비어도 5건을 채운다"""
    out = main._merge_community([], [{"title": f"r{i}"} for i in range(7)], limit=5)
    assert [i["title"] for i in out] == ["r0", "r1", "r2", "r3", "r4"]


def test_collect_merges_community_into_five():
    """HN·Reddit 을 합쳐 5건만 싣는다"""
    hn = [{"title": f"h{i}", "url": f"http://h{i}", "points": 10} for i in range(4)]
    rd = [{"title": f"r{i}", "url": f"http://r{i}", "source": "r/x"} for i in range(4)]
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", return_value=hn), \
         patch("main.fetch_all_reddit", return_value=rd), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-09-20")
    assert [i["title"] for i in data["community"]] == ["h0", "r0", "h1", "r1", "h2"]


def test_collect_survives_hn_failure():
    """한 소스가 죽어도 배치는 계속된다"""
    rd = [{"title": "r0", "url": "http://r0", "source": "r/x"}]
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", side_effect=RuntimeError("HN 503")), \
         patch("main.fetch_all_reddit", return_value=rd), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-09-20")
    assert [i["title"] for i in data["community"]] == ["r0"]


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


def test_analyze_items_runs_in_parallel(monkeypatch):
    import time
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
    monkeypatch.setattr(main, "ENABLE_SVG", False)
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
