from datetime import datetime
from config import KST
from unittest.mock import MagicMock, patch

import pytest
import requests
from sources import hackernews


def _story(rank, story_id, title, href, points, comments):
    return f'''<tr class="athing submission" id="{story_id}">
      <td class="title"><span class="rank">{rank}.</span></td>
      <td class="title"><span class="titleline"><a href="{href}">{title}</a>
        <span class="sitebit"><a href="from?site=example.com">example.com</a></span>
      </span></td></tr>
      <tr><td colspan="2"></td><td class="subtext"><span class="subline">
        <span class="score" id="score_{story_id}">{points} points</span>
        by <a href="user?id=author">author</a>
        <span class="age"><a href="item?id={story_id}">1 hour ago</a></span> |
        <a href="item?id={story_id}">{comments}</a>
      </span></td></tr><tr class="spacer"><td></td></tr>'''


MOCK_HTML = '<html><body><table>' + ''.join([
    _story(1, 123, 'First story', 'https://example.com/first', 50, '12&nbsp;comments'),
    _story(2, 456, 'Ask HN: Second story?', 'item?id=456', 900, 'discuss'),
    _story(3, 789, 'Third story', '/item?id=789', 200, '1&nbsp;comment'),
    _story(4, 999, 'Fourth story', 'https://example.com/fourth', 9999, '300 comments'),
]) + '</table></body></html>'


def _response(html=MOCK_HTML):
    response = MagicMock()
    response.text = html
    return response


def test_official_past_page_preserves_rank_instead_of_sorting_points(monkeypatch):
    monkeypatch.setattr(hackernews, 'MAX_HN_ITEMS', 3)
    with patch('sources.hackernews.requests.get', return_value=_response()) as get:
        items = hackernews.fetch_top_stories('2026-10-26')
    get.assert_called_once_with('https://news.ycombinator.com/front',
                                params={'day': '2026-10-26'}, timeout=15)
    assert [item['rank'] for item in items] == [1, 2, 3]
    assert [item['points'] for item in items] == [50, 900, 200]
    assert items[0] == {'title': 'First story', 'url': 'https://example.com/first',
                        'points': 50, 'comments': 12,
                        'hn_url': 'https://news.ycombinator.com/item?id=123',
                        'source': 'HN', 'rank': 1, 'source_date': '2026-10-26'}
    assert items[1]['url'] == items[1]['hn_url']
    assert items[1]['comments'] == 0
    assert items[2]['url'] == items[2]['hn_url']
    assert items[2]['comments'] == 1


def test_default_day_is_yesterday_in_kst(monkeypatch):
    monkeypatch.setattr(hackernews, 'now_kst', lambda: datetime(2026, 1, 1, 0, 1, tzinfo=KST))
    with patch('sources.hackernews.requests.get', return_value=_response()) as get:
        items = hackernews.fetch_top_stories()
    assert get.call_args.kwargs['params'] == {'day': '2025-12-31'}
    assert items[0]['source_date'] == '2025-12-31'


@pytest.mark.parametrize('day', ['', '2026-02-30', '20261026', '2026-10-26T00:00:00', 123])
def test_invalid_explicit_day_does_not_make_request(day):
    with patch('sources.hackernews.requests.get') as get:
        with pytest.raises(ValueError):
            hackernews.fetch_top_stories(day)
    get.assert_not_called()


def test_http_error_is_not_silently_empty():
    response = _response()
    response.raise_for_status.side_effect = requests.HTTPError('503')
    with patch('sources.hackernews.requests.get', return_value=response):
        with pytest.raises(requests.HTTPError):
            hackernews.fetch_top_stories('2026-10-26')


@pytest.mark.parametrize('html', ['<html>Rate limited</html>', '<tr class="athing" id="123"><td>No title</td></tr>'])
def test_success_response_without_valid_stories_raises(html):
    with patch('sources.hackernews.requests.get', return_value=_response(html)):
        with pytest.raises(ValueError, match='No valid'):
            hackernews.fetch_top_stories('2026-10-26')
