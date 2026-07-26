from unittest.mock import patch, MagicMock
from sources.rss import fetch_rss_entries

def _mock_feed():
    entry = MagicMock()
    entry.title = "New Post"
    entry.link = "https://example.com/post"
    entry.get = lambda k, d="": "This is a summary." if k == "summary" else d
    entry.published_parsed = (2026, 5, 31, 12, 0, 0, 5, 151, 0)
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
