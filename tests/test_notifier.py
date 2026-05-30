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

def test_send_slack_skips_empty_url():
    with patch("notifier.requests.post") as mock_post:
        send_slack("", "2026-05-31", ["item1"])
    mock_post.assert_not_called()
