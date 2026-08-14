from unittest.mock import MagicMock, patch

import notebooklm


def test_empty_urls_returns_false():
    assert notebooklm.generate_audio_review([]) is False
    assert notebooklm.generate_audio_review(["", None]) is False


def test_requires_notebook_url(monkeypatch):
    monkeypatch.setattr(notebooklm, "NOTEBOOKLM_NOTEBOOK_URL", "")
    assert notebooklm.generate_audio_review(["http://a"]) is False


def test_browser_failure_returns_false(monkeypatch):
    """브라우저가 죽어도 예외를 밖으로 던지지 않는다 — 배치가 멈추면 안 된다"""
    monkeypatch.setattr(notebooklm, "NOTEBOOKLM_NOTEBOOK_URL", "http://nb")
    monkeypatch.setattr(notebooklm, "_run",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert notebooklm.generate_audio_review(["http://a"]) is False


def test_passes_title_into_prompt(monkeypatch):
    got = {}
    monkeypatch.setattr(notebooklm, "NOTEBOOKLM_NOTEBOOK_URL", "http://nb")
    monkeypatch.setattr(notebooklm, "_run",
                        lambda urls, prompt: got.update(urls=urls, prompt=prompt) or True)
    assert notebooklm.generate_audio_review(["http://a"], title="2026-08-14 기술 트렌드") is True
    assert got["urls"] == ["http://a"]
    assert "2026-08-14" in got["prompt"]


def test_no_prompt_without_title(monkeypatch):
    got = {}
    monkeypatch.setattr(notebooklm, "NOTEBOOKLM_NOTEBOOK_URL", "http://nb")
    monkeypatch.setattr(notebooklm, "_run", lambda urls, prompt: got.update(prompt=prompt) or True)
    notebooklm.generate_audio_review(["http://a"])
    assert got["prompt"] == ""


# ── UI 조작 헬퍼 ──

def test_click_any_tries_each_label():
    """UI 언어가 한국어일 수도 영어일 수도 있어 후보를 차례로 시도한다"""
    page = MagicMock()
    tried = []

    def get_by_role(role, name=None, exact=None):
        tried.append(name)
        loc = MagicMock()
        if name == "Add source":
            loc.first.wait_for.return_value = None
            loc.first.click.return_value = None
        else:
            loc.first.wait_for.side_effect = RuntimeError("not found")
        return loc

    page.get_by_role.side_effect = get_by_role
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("not found")
    assert notebooklm._click_any(page, ["출처 추가", "Add source"]) is True
    assert "출처 추가" in tried and "Add source" in tried


def test_click_any_returns_false_when_nothing_matches():
    page = MagicMock()
    page.get_by_role.return_value.first.wait_for.side_effect = RuntimeError("no")
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._click_any(page, ["없는버튼"]) is False


def test_fill_urls_joins_with_newlines():
    """이 화면은 '여러 URL을 추가하려면 줄 바꿈으로 구분하세요'라고 안내한다"""
    page = MagicMock()
    box = MagicMock()
    page.get_by_placeholder.return_value.first = box
    assert notebooklm._fill_urls(page, ["http://a", "http://b"]) is True
    box.fill.assert_called_once_with("http://a\nhttp://b")


def test_fill_urls_falls_back_to_textarea():
    page = MagicMock()
    page.get_by_placeholder.return_value.first.wait_for.side_effect = RuntimeError("no")
    ta = MagicMock()
    page.locator.return_value.first = ta
    assert notebooklm._fill_urls(page, ["http://a"]) is True
    ta.fill.assert_called_once_with("http://a")


def test_fill_urls_returns_false_when_no_input():
    page = MagicMock()
    page.get_by_placeholder.return_value.first.wait_for.side_effect = RuntimeError("no")
    page.locator.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._fill_urls(page, ["http://a"]) is False


def test_format_labels_cover_all_options():
    """실제 화면의 형식 4종과 대응해야 한다"""
    assert set(notebooklm._FORMATS) == {"deep_dive", "summary", "criticism", "debate"}
    assert "심층 분석" in notebooklm._FORMATS["deep_dive"]
    assert "토론" in notebooklm._FORMATS["debate"]


def test_labels_include_korean_and_english():
    for key in ("add_source", "website", "insert", "audio_overview", "generate"):
        labels = notebooklm._L[key]
        assert any(any("가" <= ch <= "힣" for ch in l) for l in labels), key
        assert any(l.isascii() for l in labels), key
