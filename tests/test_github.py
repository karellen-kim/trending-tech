from unittest.mock import patch, MagicMock
from sources.github import fetch_trending

MOCK_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/microsoft/phi-4">microsoft / <strong>phi-4</strong></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A small language model</p>
  <span class="float-sm-right">
    <a href="/microsoft/phi-4/stargazers">1,234 stars today</a>
  </span>
</article>
"""

def test_fetch_trending_returns_list():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_HTML
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.github.requests.get", return_value=mock_resp):
        items = fetch_trending()
    assert isinstance(items, list)

def test_fetch_trending_parses_repo():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_HTML
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.github.requests.get", return_value=mock_resp):
        items = fetch_trending()
    assert len(items) == 1
    assert items[0]["name"] == "microsoft/phi-4"
    assert items[0]["url"] == "https://github.com/microsoft/phi-4"
    assert "small language model" in items[0]["description"]
