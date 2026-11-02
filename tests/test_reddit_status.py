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
def source(monkeypatch, tmp_path):
    monkeypatch.setattr(reddit, 'REDDIT_SUBREDDITS', ['one', 'two'])
    monkeypatch.setattr(reddit, 'STATE_DIR', tmp_path / 'reddit', raising=False)
    clock = [datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr(reddit, '_utc_now', lambda: datetime.fromtimestamp(clock[0], timezone.utc))
    sleep = Mock(side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
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
    assert get.call_count == 4  # N first attempts plus two shared retries
    assert all(value['attempts'] == 2 for value in result['sources'])
    assert all(value['reason'] == 'request_budget_exhausted' for value in result['sources'])
    assert sum(call.args[0] for call in source.call_args_list) <= 30


def test_six_sources_get_first_attempt_before_retries(source, monkeypatch):
    monkeypatch.setattr(reddit, 'REDDIT_SUBREDDITS', ['one', 'two', 'three', 'four', 'five', 'six'])
    get = Mock(side_effect=[response(), response(429), *[response() for _ in range(4)],
                            response(429), response(429)])
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    names = [call.args[0].split('/r/')[1].split('/')[0] for call in get.call_args_list]
    assert names == ['one', 'two', 'three', 'four', 'five', 'six', 'two', 'two']
    assert [s['status'] for s in result['sources']] == ['success', 'failed', *['success'] * 4]
    assert result['sources'][1]['reason'] == 'retries_exhausted'
    assert result['status'] == 'partial'
    assert sum(s['retry_wait_seconds'] for s in result['sources']) <= 30


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


def test_cooldown_survives_next_run_and_expires(source, monkeypatch):
    get = Mock(return_value=response(429, '3600'))
    monkeypatch.setattr(reddit.requests, 'get', get)
    reddit.fetch_all_reddit()
    result = reddit.fetch_all_reddit()
    assert get.call_count == 1
    assert all(s['attempts'] == 0 and s['reason'] == 'wait_budget_exceeded' for s in result['sources'])
    source(3600)
    get.return_value = response()
    assert reddit.fetch_all_reddit()['status'] == 'success'
    assert get.call_count == 3


def test_last_429_persists_cooldown(source, monkeypatch):
    get = Mock(return_value=response(429))
    monkeypatch.setattr(reddit.requests, 'get', get)
    reddit.fetch_all_reddit()
    from json import loads
    state = loads((reddit.STATE_DIR / 'state.json').read_text())
    assert state['next_allowed_at'] > reddit._utc_now().timestamp()


def test_corrupt_state_does_not_issue_http(source, monkeypatch):
    reddit.STATE_DIR.mkdir()
    (reddit.STATE_DIR / 'state.json').write_text('{broken')
    get = Mock()
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    get.assert_not_called()
    assert result['status'] == 'failed'
    assert all(s['reason'] == 'coordination_unavailable' for s in result['sources'])


def test_request_evidence_contains_only_safe_limit_headers(source, monkeypatch):
    limited = response(429, '2')
    limited.headers.update({'X-Ratelimit-Remaining': '0', 'X-Ratelimit-Reset': '60',
                            'Set-Cookie': 'private-token', 'X-Ratelimit-Used': 'private-token'})
    monkeypatch.setattr(reddit.requests, 'get', Mock(side_effect=[limited, response(), response()]))
    result = reddit.fetch_all_reddit()
    request = result['sources'][0]['requests'][0]
    assert request['requested_at'] and request['http_status'] == 429
    assert request['rate_limit_headers'] == {'x-ratelimit-remaining': 0.0, 'x-ratelimit-reset': 60.0}
    assert 'private-token' not in str(result)


def test_another_process_cannot_collect_while_lock_is_held(source, monkeypatch):
    import subprocess
    import sys
    reddit.STATE_DIR.mkdir()
    child = subprocess.Popen([sys.executable, '-c',
        'import fcntl, sys; f = open(sys.argv[1], "a"); '
        'fcntl.flock(f, fcntl.LOCK_EX); print("locked", flush=True); sys.stdin.read()',
        str(reddit.STATE_DIR / 'collection.lock')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'locked'
        get = Mock()
        monkeypatch.setattr(reddit.requests, 'get', get)
        result = reddit.fetch_all_reddit()
        get.assert_not_called()
        assert all(s['reason'] == 'collection_in_progress' for s in result['sources'])
    finally:
        child.communicate(input='', timeout=5)
    assert child.returncode == 0
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response()))
    assert reddit.fetch_all_reddit()['status'] == 'success'


def test_last_state_save_failure_is_not_success(source, monkeypatch):
    get = Mock(return_value=response())
    monkeypatch.setattr(reddit.requests, 'get', get)
    save = reddit._save_limit
    calls = []
    def fail_last(state):
        calls.append(state)
        if len(calls) == 2:
            raise OSError('private-path')
        save(state)
    monkeypatch.setattr(reddit, '_save_limit', fail_last)
    result = reddit.fetch_all_reddit()
    assert result['status'] != 'success'
    assert result['sources'][-1]['reason'] == 'coordination_unavailable'
    assert 'private-path' not in str(result)


def test_cooldown_is_shared_with_a_separate_collector_process(source, monkeypatch):
    import subprocess
    import sys
    script = '''
import sys, requests
from pathlib import Path
from sources import reddit
reddit.STATE_DIR = Path(sys.argv[1])
reddit.REDDIT_SUBREDDITS = ['one']
r = requests.Response()
r.status_code = 429
r.headers['Retry-After'] = '3600'
reddit.requests.get = lambda *a, **kw: r
assert reddit.fetch_all_reddit()['status'] == 'failed'
'''
    completed = subprocess.run([sys.executable, '-c', script, str(reddit.STATE_DIR)],
                               capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, completed.stderr
    get = Mock()
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    get.assert_not_called()
    assert all(s['reason'] == 'wait_budget_exceeded' for s in result['sources'])


def test_all_six_limited_sources_stay_within_global_budgets(source, monkeypatch):
    monkeypatch.setattr(reddit, 'REDDIT_SUBREDDITS', list('abcdef'))
    get = Mock(return_value=response(429))
    monkeypatch.setattr(reddit.requests, 'get', get)
    result = reddit.fetch_all_reddit()
    assert get.call_count == 8
    assert all(1 <= s['attempts'] <= 3 for s in result['sources'])
    assert sum(s['retry_wait_seconds'] for s in result['sources']) <= 30
    assert sum(call.args[0] for call in source.call_args_list) <= 30
    assert result['status'] == 'failed'
