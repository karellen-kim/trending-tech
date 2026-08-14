from unittest.mock import Mock, patch

import notebooklm


def _resp(payload, status=200):
    r = Mock(status_code=status)
    r.json = Mock(return_value=payload)
    r.raise_for_status = Mock()
    r.content = b"AUDIO"
    return r


def test_uploads_urls_as_source_objects():
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent[url] = json
        if url.endswith("/sources/upload"):
            return _resp({"overall_success": True, "results": []})
        if url.endswith("/audio/generate"):
            return _resp({"job_id": "j1", "status": "pending"})
        return _resp({"success": True, "count": 0})

    with patch("notebooklm.requests.post", side_effect=fake_post), \
         patch("notebooklm.requests.get", return_value=_resp(
             {"job_id": "j1", "status": "completed", "download_url": "/x"})), \
         patch("notebooklm.open", create=True):
        notebooklm.generate_audio_review(["http://a", "http://b"], "/tmp/x.mp3")

    body = sent[f"{notebooklm.NOTEBOOKLM_API_URL}/sources/upload"]
    assert body == {"sources": [{"type": "url", "content": "http://a"},
                                {"type": "url", "content": "http://b"}]}


def test_clears_sources_before_upload():
    """노트북 하나를 재사용하므로 어제 소스를 먼저 비워야 한다"""
    order = []

    def fake_post(url, json=None, timeout=None):
        order.append(url.split("/")[-2] + "/" + url.split("/")[-1])
        if url.endswith("/audio/generate"):
            return _resp({"job_id": "j1", "status": "pending"})
        return _resp({"success": True, "count": 1, "overall_success": True, "results": []})

    with patch("notebooklm.requests.post", side_effect=fake_post), \
         patch("notebooklm.requests.get", return_value=_resp(
             {"status": "completed", "download_url": "/x"})), \
         patch("notebooklm.open", create=True):
        notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3")

    assert order[0] == "sources/clear", order
    assert order[1] == "sources/upload", order


def test_returns_none_when_server_unreachable():
    import requests
    with patch("notebooklm.requests.post", side_effect=requests.ConnectionError("no server")):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3") is None


def test_returns_none_on_failed_job():
    with patch("notebooklm.requests.post",
               return_value=_resp({"job_id": "j", "status": "pending",
                                   "success": True, "overall_success": True, "results": []})), \
         patch("notebooklm.requests.get", return_value=_resp({"status": "failed", "error": "boom"})):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3") is None


def test_polls_until_completed():
    states = [{"status": "pending"}, {"status": "processing"},
              {"status": "completed", "download_url": "/x"}]
    calls = []

    def fake_get(url, timeout=None):
        if "/status/" in url:
            calls.append(url)
            return _resp(states[min(len(calls) - 1, len(states) - 1)])
        return _resp({})

    with patch("notebooklm.requests.post",
               return_value=_resp({"job_id": "j", "status": "pending",
                                   "success": True, "overall_success": True, "results": []})), \
         patch("notebooklm.requests.get", side_effect=fake_get), \
         patch("notebooklm.time.sleep"), patch("notebooklm.open", create=True):
        out = notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3")
    assert len(calls) == 3
    assert out == "/tmp/x.mp3"


def test_gives_up_after_timeout():
    """폴링이 끝나지 않아도 정해진 시간에 포기해야 한다 (실제로 기다리지 않게 시계를 가짜로 돌린다)"""
    ticks = iter([0, 10, 20, 40, 60, 80])
    with patch("notebooklm.requests.post",
               return_value=_resp({"job_id": "j", "status": "pending",
                                   "success": True, "overall_success": True, "results": []})), \
         patch("notebooklm.requests.get", return_value=_resp({"status": "processing"})), \
         patch("notebooklm.time.sleep"), \
         patch("notebooklm.time.monotonic", side_effect=lambda: next(ticks)):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3", timeout=30) is None


def test_empty_urls_returns_none():
    assert notebooklm.generate_audio_review([], "/tmp/x.mp3") is None
    assert notebooklm.generate_audio_review(["", None], "/tmp/x.mp3") is None


def test_missing_job_id_returns_none():
    with patch("notebooklm.requests.post",
               return_value=_resp({"success": True, "overall_success": True, "results": []})):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3") is None
