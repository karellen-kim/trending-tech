from unittest.mock import patch
import main


def test_collect_excludes_hn_and_reddit():
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-08-14")
    assert "hn" not in data
    assert "reddit" not in data


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
