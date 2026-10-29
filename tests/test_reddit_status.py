"""Reddit 제한 응답은 실제 대기나 네트워크 없이 재현한다."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from sources import reddit


def response(code=200, retry_after=None):
    value = requests.Response()
    value.status_code = code
    value._content = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    if retry_after is not None:
        value.headers['Retry-After'] = retry_after
    return value


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(reddit, 'REDDIT_SUBREDDITS', ['one', 'two'])
    sleep = Mock()
    monkeypatch.setattr(reddit, 'sleep', sleep)
    return sleep


def test_retry_after_then_success(source, monkeypatch):
    get = Mock(side_effect=[response(429, '2'), response(), response()])
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert result['status'] == 'success'
    assert result['sources'][0]['attempts'] == 2
    assert result['sources'][0]['count'] == 0
    assert source.call_args_list[0].args == (2,)


def test_long_retry_after_stops_all_remaining_requests(source, monkeypatch):
    get = Mock(return_value=response(429, '3600'))
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert get.call_count == 1
    assert result['status'] == 'failed'
    assert result['sources'][0]['http_status'] == 429
    assert result['sources'][1]['status'] == 'skipped_rate_limit'
    source.assert_not_called()


def test_persistent_limit_is_bounded_across_subreddits(source, monkeypatch):
    get = Mock(return_value=response(429))
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert get.call_count == 3
    assert result['sources'][0]['attempts'] == 3
    assert result['sources'][1]['status'] == 'skipped_rate_limit'
    assert sum(call.args[0] for call in source.call_args_list) <= 30


def test_partial_failure_and_normal_empty_are_distinct(source, monkeypatch):
    get = Mock(side_effect=[response(403), response()])
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert result['status'] == 'partial'
    assert [value['status'] for value in result['sources']] == ['failed', 'success']
    assert result['items'] == []


def test_timeout_is_safe_structured_failure(source, monkeypatch):
    monkeypatch.setattr(reddit.requests, 'get', Mock(side_effect=requests.Timeout('private-url-token')))
    result = reddit.fetch_all_reddit()
    assert result['status'] == 'failed'
    assert 'private-url-token' not in str(result)


@pytest.mark.parametrize('header', ['Thu, 29 Oct 2026 00:00:05 GMT',
                                  'Thursday, 29-Oct-26 00:00:05 GMT',
                                  'Thu Oct 29 00:00:05 2026'])
def test_http_date_retry_after(source, monkeypatch, header):
    monkeypatch.setattr(reddit, '_utc_now', lambda: datetime(2026, 10, 29, 0, 0, 0, tzinfo=timezone.utc), raising=False)
    monkeypatch.setattr(reddit.requests, 'get', Mock(side_effect=[
        response(429, header), response(), response()]))
    assert reddit.fetch_all_reddit()['status'] == 'success'
    assert source.call_args_list[0].args == (5,)


@pytest.mark.parametrize('header', [None, 'invalid', '-1', 'NaN', '²'])
def test_missing_or_invalid_header_uses_bounded_backoff(source, monkeypatch, header):
    monkeypatch.setattr(reddit.requests, 'get', Mock(side_effect=[response(429, header), response(), response()]))
    assert reddit.fetch_all_reddit()['status'] == 'success'
    assert source.call_args_list[0].args == (2,)


def test_wait_budget_is_shared_across_subreddits(source, monkeypatch):
    get = Mock(side_effect=[response(429, '20'), response(), response(429, '20')])
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert result['status'] == 'partial'
    assert get.call_count == 3
    assert sum(call.args[0] for call in source.call_args_list) == 21


def test_partial_result_preserves_successful_items(source, monkeypatch):
    good = {'title': 'Good', 'url': 'https://example.test/good'}
    monkeypatch.setattr(reddit, 'fetch_subreddit', Mock(side_effect=[[good], requests.Timeout()]))
    result = reddit.fetch_all_reddit()
    assert result['items'] == [good]
    assert result['status'] == 'partial'


def test_invalid_feed_is_failure_instead_of_empty_success(source, monkeypatch):
    bad = response()
    bad._content = b'<html>blocked</html>'
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=bad))
    assert reddit.fetch_all_reddit()['status'] == 'failed'
