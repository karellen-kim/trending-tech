from unittest.mock import patch, MagicMock
from sources.hackernews import fetch_top_stories

MOCK_RESPONSE = {
    "hits": [{
        "objectID": "123",
        "title": "LLaMA 4 Released",
        "url": "https://example.com/llama4",
        "points": 500,
        "num_comments": 200,
    }]
}

def test_fetch_top_stories_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.hackernews.requests.get", return_value=mock_resp):
        items = fetch_top_stories()
    assert isinstance(items, list)

def test_fetch_top_stories_parses_item():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.hackernews.requests.get", return_value=mock_resp):
        items = fetch_top_stories()
    assert items[0]["title"] == "LLaMA 4 Released"
    assert items[0]["url"] == "https://example.com/llama4"
    assert items[0]["points"] == 500
    assert items[0]["comments"] == 200
    assert items[0]["hn_url"] == "https://news.ycombinator.com/item?id=123"
