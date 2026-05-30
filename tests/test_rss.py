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
    with patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert isinstance(items, list)

def test_fetch_rss_entries_parses_entry():
    with patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert len(items) == 1
    assert items[0]["title"] == "New Post"
    assert items[0]["url"] == "https://example.com/post"
    assert items[0]["source"] == "Test Blog"
    assert "summary" in items[0]
