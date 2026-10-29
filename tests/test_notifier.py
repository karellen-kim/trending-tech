from unittest.mock import patch, MagicMock
from notifier import send_slack

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
    response = MagicMock(status_code=429, text='private response body')
    with patch('notifier.requests.post', return_value=response):
        with pytest.raises(RuntimeError) as error:
            send_slack('https://hooks.slack.com/private-token', '2026-10-29', [])
    assert 'private' not in str(error.value)
    assert '429' in str(error.value)


def test_slack_returns_explicit_evidence():
    with patch('notifier.requests.post', return_value=MagicMock(status_code=200)):
        assert send_slack('https://hooks.slack.com/test', '2026-10-29', []) == {
            'status': 'success', 'http_status': 200}
    assert send_slack('', '2026-10-29', []) == {'status': 'skipped', 'reason': 'not_configured'}


def test_network_failure_hides_webhook_exception():
    import pytest
    import requests
    with patch('notifier.requests.post', side_effect=requests.Timeout('private-webhook-url')):
        with pytest.raises(RuntimeError, match='^Slack request failed$'):
            send_slack('https://hooks.slack.com/private-token', '2026-10-29', [])
