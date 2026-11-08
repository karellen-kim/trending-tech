from unittest.mock import patch, MagicMock
from notifier import send_slack
import pytest
import requests

def test_send_slack_posts_to_webhook():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("notifier.requests.post", return_value=mock_resp) as mock_post:
        send_slack("https://hooks.slack.com/test", "2026-05-31", ["LLaMA 4", "phi-4"])
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "2026-05-31" in payload["text"]
    assert "karellen-kim.github.io/trending-tech" in payload["text"]

def test_send_slack_skips_empty_url():
    with patch("notifier.requests.post") as mock_post:
        send_slack("", "2026-05-31", ["item1"])
    mock_post.assert_not_called()


def test_http_failure_raises_without_response_body_or_webhook():
    import pytest
    response = MagicMock(status_code=400, text='private response body')
    with patch('notifier.requests.post', return_value=response):
        with pytest.raises(RuntimeError) as error:
            send_slack('https://hooks.slack.com/private-token', '2026-10-29', [])
    assert 'private' not in str(error.value)
    assert '400' in str(error.value)


def test_slack_returns_explicit_evidence():
    with patch('notifier.requests.post', return_value=MagicMock(status_code=200)):
        assert send_slack('https://hooks.slack.com/test', '2026-10-29', []) == {
            'status': 'success', 'http_status': 200, 'attempts': 1,
            'retry_wait_seconds': 0, 'delivery_state': 'acknowledged'}
    assert send_slack('', '2026-10-29', []) == {'status': 'skipped', 'reason': 'not_configured'}


def test_network_failure_hides_webhook_exception():
    import pytest
    import requests
    with patch('notifier.requests.post', side_effect=requests.Timeout('private-webhook-url')):
        with pytest.raises(RuntimeError, match='^Slack request failed$'):
            send_slack('https://hooks.slack.com/private-token', '2026-10-29', [])


def test_connect_timeout_retries_before_delivery():
    with patch('notifier.requests.post', side_effect=[requests.ConnectTimeout('secret'),
            MagicMock(status_code=200)]) as post, patch('notifier.time.sleep') as sleep:
        assert send_slack('secret-webhook', '2026-11-07', []) == {
            'status': 'success', 'http_status': 200, 'attempts': 2,
            'retry_wait_seconds': 1, 'delivery_state': 'acknowledged'}
    assert post.call_count == 2
    sleep.assert_called_once_with(1)


def test_connect_timeout_attempts_are_bounded_and_recorded():
    with patch('notifier.requests.post', side_effect=requests.ConnectTimeout('secret')) as post, \
            patch('notifier.time.sleep') as sleep, patch('notifier.record_stage') as stage:
        with pytest.raises(RuntimeError, match='^Slack request failed$'):
            send_slack('secret-webhook', '2026-11-07', [])
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    assert stage.call_args.kwargs == {'attempts': 3, 'error_kind': 'connect_timeout',
        'delivery_state': 'not_sent', 'retry_wait_seconds': 3}


def test_rate_limit_respects_retry_after():
    response = MagicMock(status_code=429, headers={'Retry-After': '4'})
    with patch('notifier.requests.post', side_effect=[response, MagicMock(status_code=200)]) as post, \
            patch('notifier.time.sleep') as sleep:
        send_slack('secret-webhook', '2026-11-07', [])
    assert post.call_count == 2
    sleep.assert_called_once_with(4)


@pytest.mark.parametrize('header,expected_attempts,waits', [('20', 2, [20]), ('31', 1, []),
    ('nan', 3, [1, 2]), ('invalid', 3, [1, 2])])
def test_rate_limit_total_wait_is_bounded(header, expected_attempts, waits):
    response = MagicMock(status_code=429, headers={'Retry-After': header})
    with patch('notifier.requests.post', return_value=response) as post, \
            patch('notifier.time.sleep') as sleep, patch('notifier.record_stage') as stage:
        with pytest.raises(RuntimeError, match='^Slack HTTP 429$'):
            send_slack('secret-webhook', '2026-11-07', [])
    assert post.call_count == expected_attempts
    assert [call.args[0] for call in sleep.call_args_list] == waits
    assert stage.call_args.kwargs['delivery_state'] == 'rejected'
    assert stage.call_args.kwargs['retry_wait_seconds'] <= 30


@pytest.mark.parametrize('error,kind', [(requests.ReadTimeout('secret'), 'read_timeout'),
    (requests.ConnectionError('secret'), 'connection_error'),
    (requests.exceptions.SSLError('secret'), 'tls_error'),
    (requests.Timeout('secret'), 'request_error')])
def test_ambiguous_network_failure_is_not_retried(error, kind):
    with patch('notifier.requests.post', side_effect=error) as post, \
            patch('notifier.time.sleep') as sleep, patch('notifier.record_stage') as stage:
        with pytest.raises(RuntimeError) as caught:
            send_slack('secret-webhook', '2026-11-07', [])
    post.assert_called_once()
    sleep.assert_not_called()
    assert 'secret' not in str(caught.value)
    assert 'secret' not in repr(stage.call_args)
    assert stage.call_args.kwargs['error_kind'] == kind
    assert stage.call_args.kwargs['delivery_state'] == 'unknown'


def test_server_error_is_not_retried_and_delivery_is_unknown():
    with patch('notifier.requests.post', return_value=MagicMock(status_code=503)) as post, \
            patch('notifier.record_stage') as stage:
        with pytest.raises(RuntimeError, match='^Slack HTTP 503$'):
            send_slack('secret-webhook', '2026-11-07', [])
    post.assert_called_once()
    assert stage.call_args.kwargs['delivery_state'] == 'unknown'
    assert stage.call_args.kwargs['http_status'] == 503


def test_failure_evidence_survives_run_receipt(tmp_path):
    import json
    from run_receipt import RunReceipt

    with patch('notifier.requests.post', side_effect=requests.ReadTimeout('secret-webhook')):
        with pytest.raises(RuntimeError):
            with RunReceipt(tmp_path, '2026-11-07'):
                send_slack('secret-webhook', '2026-11-07', [])
    raw = next(tmp_path.glob('*.json')).read_text()
    assert 'secret' not in raw
    state = json.loads(raw)
    assert state['status'] == 'failed'
    assert state['stages']['slack'] == {'status': 'failed', 'attempts': 1,
        'retry_wait_seconds': 0, 'error_kind': 'read_timeout', 'delivery_state': 'unknown'}


def test_retry_success_evidence_survives_final_stage_replacement(tmp_path):
    import json
    from run_receipt import RunReceipt

    with patch('notifier.requests.post', side_effect=[requests.ConnectTimeout('secret-webhook'),
            MagicMock(status_code=200)]), patch('notifier.time.sleep'):
        with RunReceipt(tmp_path, '2026-11-07') as run:
            result = send_slack('secret-webhook', '2026-11-07', [])
            run.stage('slack', **result)
    raw = next(tmp_path.glob('*.json')).read_text()
    assert 'secret' not in raw
    assert json.loads(raw)['stages']['slack'] == {'status': 'success', 'http_status': 200,
        'attempts': 2, 'retry_wait_seconds': 1, 'delivery_state': 'acknowledged'}
