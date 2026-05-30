from unittest.mock import patch, MagicMock
from sources.arxiv import fetch_arxiv_papers

def _mock_feed():
    entry = MagicMock()
    entry.title = "Attention Is All You Need 2.0"
    entry.link = "https://arxiv.org/abs/2601.00001"
    entry.get = lambda k, d="": "Abstract of the paper about transformers." if k == "summary" else d
    feed = MagicMock()
    feed.entries = [entry]
    return feed

def test_fetch_arxiv_papers_returns_list():
    with patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert isinstance(items, list)

def test_fetch_arxiv_papers_parses_entry():
    with patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert items[0]["title"] == "Attention Is All You Need 2.0"
    assert "arxiv.org" in items[0]["url"]
    assert "abstract" in items[0]
