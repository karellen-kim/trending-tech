from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from sources.rss import fetch_rss_entries

KST = timezone(timedelta(hours=9))

def _mock_feed():
    entry = MagicMock()
    entry.title = "New Post"
    entry.link = "https://example.com/post"
    entry.get = lambda k, d="": "This is a summary." if k == "summary" else d
    # 고정 날짜를 쓰면 수집 범위(COLLECT_DAYS) 밖으로 밀려나므로 오늘 기준으로 만든다
    entry.published_parsed = datetime.now(timezone.utc).timetuple()
    feed = MagicMock()
    feed.entries = [entry]
    return feed

def test_fetch_rss_entries_returns_list():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp), \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert isinstance(items, list)

def test_fetch_rss_entries_parses_entry():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp), \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert len(items) == 1
    assert items[0]["title"] == "New Post"
    assert items[0]["url"] == "https://example.com/post"
    assert items[0]["source"] == "Test Blog"
    assert "summary" in items[0]

def test_fetch_rss_entries_uses_timeout():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp) as mock_get, \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert mock_get.call_args.kwargs.get("timeout") == 15


def _feed_xml(dates):
    items = "".join(
        f"<item><title>t{i}</title><link>http://x/{i}</link>"
        f"<description>본문{i}</description><pubDate>{d}</pubDate></item>"
        for i, d in enumerate(dates)
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>".encode()


def _mock_resp(dates):
    resp = Mock(status_code=200, content=_feed_xml(dates))
    resp.raise_for_status = Mock()
    return resp


def test_returns_only_top_3_entries():
    """최신 3건만 가져온다 — 4번째부터는 보지 않는다"""
    from sources import rss
    d = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([d] * 10)):
        items = rss.fetch_rss_entries("s", "http://f", max_items=3)
    assert len(items) == 3


def test_filters_old_entries_in_code():
    """실측상 171건 전부 날짜 파싱이 되므로, 오래된 글은 LLM 없이 여기서 걸러낸다"""
    from sources import rss
    old = (datetime.now(KST) - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([old])):
        items = rss.fetch_rss_entries("s", "http://f")
    assert items == []


def test_keeps_yesterday_entry():
    """COLLECT_DAYS=2 이므로 어제 글도 포함한다"""
    from sources import rss
    y = (datetime.now(KST) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([y])):
        items = rss.fetch_rss_entries("s", "http://f")
    assert len(items) == 1
    assert items[0]["date_verified"] is True


def test_rejects_future_dated_entry():
    """발행일을 미래로 찍은 글이 매일 다시 올라오면 안 된다"""
    from sources import rss
    future = (datetime.now(KST) + timedelta(days=3)).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([future])):
        items = rss.fetch_rss_entries("s", "http://f")
    assert items == []


def test_entry_without_date_passes_through_for_llm():
    """날짜를 못 읽은 항목만 LLM 판정 대상으로 넘긴다"""
    from sources import rss
    xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
           b"<item><title>t</title><link>http://x</link><description>d</description></item>"
           b"</channel></rss>")
    resp = Mock(status_code=200, content=xml)
    resp.raise_for_status = Mock()
    with patch("sources.rss.requests.get", return_value=resp):
        items = rss.fetch_rss_entries("s", "http://f")
    assert len(items) == 1
    assert items[0]["date_verified"] is False


def test_pub_hint_carries_parsed_date():
    """고정 날짜를 쓰면 수집 범위(COLLECT_DAYS) 밖으로 밀려나 시간이 지나면 깨진다"""
    from sources import rss
    now = datetime.now(KST).replace(hour=1, minute=0, second=0, microsecond=0)
    d = now.strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([d])):
        items = rss.fetch_rss_entries("s", "http://f")
    hint = items[0]["pub_hint"]
    assert now.strftime("%Y-%m-%d") in hint, hint
    assert now.strftime("%d %b %Y") in hint, hint


def test_enrich_fetches_body_only_for_short_summaries(monkeypatch):
    from sources import rss
    calls = []
    monkeypatch.setattr(rss, "_fetch_article_text",
                        lambda url, max_chars=2000: calls.append(url) or "본문 " * 200)
    items = [
        {"title": "짧음", "url": "http://a", "summary": "짧은 티저", "source": "s"},
        {"title": "충분", "url": "http://b", "summary": "가" * 300, "source": "s"},
    ]
    out = rss.enrich_with_body(items, max_fetch=10)
    assert calls == ["http://a"]
    assert len(out[0]["content"]) > 150
    assert "content" not in out[1]


def test_enrich_respects_max_fetch(monkeypatch):
    from sources import rss
    calls = []
    monkeypatch.setattr(rss, "_fetch_article_text",
                        lambda url, max_chars=2000: calls.append(url) or "x" * 400)
    items = [{"title": str(i), "url": f"http://{i}", "summary": "", "source": "s"} for i in range(10)]
    rss.enrich_with_body(items, max_fetch=3)
    assert len(calls) == 3


def test_enrich_ignores_html_tags_when_measuring():
    """<p><br/></p> 같은 껍데기는 150자를 넘어도 본문이 아니다"""
    from sources import rss
    assert rss._text_len("<p>" + "<br/>" * 60 + "</p>") < 150


def test_fetch_all_blogs_runs_in_parallel(monkeypatch):
    import time
    from sources import rss
    monkeypatch.setattr(rss, "RSS_SOURCES",
                        [{"name": f"s{i}", "url": f"http://x/{i}", "category": "dev"} for i in range(8)])
    monkeypatch.setattr(rss, "enrich_with_body", lambda items, **kw: items)

    def slow(name, url, **kw):
        time.sleep(0.3)
        return [{"title": name, "url": url, "source": name, "summary": "", "category": "dev"}]

    monkeypatch.setattr(rss, "fetch_rss_entries", slow)
    t0 = time.monotonic()
    items = rss.fetch_all_blogs()
    assert len(items) == 8
    assert time.monotonic() - t0 < 1.2


def test_fetch_all_blogs_survives_one_failure(monkeypatch):
    from sources import rss
    monkeypatch.setattr(rss, "RSS_SOURCES", [
        {"name": "ok", "url": "http://ok", "category": "dev"},
        {"name": "bad", "url": "http://bad", "category": "dev"},
    ])
    monkeypatch.setattr(rss, "enrich_with_body", lambda items, **kw: items)

    def maybe_fail(name, url, **kw):
        if name == "bad":
            raise RuntimeError("boom")
        return [{"title": "t", "url": url, "source": name, "summary": "", "category": "dev"}]

    monkeypatch.setattr(rss, "fetch_rss_entries", maybe_fail)
    assert len(rss.fetch_all_blogs()) == 1


def test_pub_hint_is_unknown_when_feed_has_no_date():
    from sources import rss
    xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
           b"<item><title>t</title><link>http://x</link><description>d</description></item>"
           b"</channel></rss>")
    resp = Mock(status_code=200, content=xml)
    resp.raise_for_status = Mock()
    with patch("sources.rss.requests.get", return_value=resp):
        items = rss.fetch_rss_entries("s", "http://f")
    assert items[0]["pub_hint"] == "unknown"
