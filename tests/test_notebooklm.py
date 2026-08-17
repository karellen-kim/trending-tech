from unittest.mock import MagicMock, patch

import notebooklm


def test_empty_urls_returns_empty():
    assert notebooklm.generate_audio_review([]) == ""
    assert notebooklm.generate_audio_review(["", None]) == ""


def test_returns_created_notebook_url(monkeypatch):
    """매번 새 노트북을 만들고 그 주소를 돌려준다 — 페이지에 링크를 걸어야 한다"""
    monkeypatch.setattr(notebooklm, "_run", lambda *a, **kw: "https://notebook.google.com/notebook/xyz")
    assert notebooklm.generate_audio_review(["http://a"]) == "https://notebook.google.com/notebook/xyz"


def test_browser_failure_returns_empty(monkeypatch):
    """브라우저가 죽어도 예외를 밖으로 던지지 않는다 — 배치가 멈추면 안 된다"""
    monkeypatch.setattr(notebooklm, "_run",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert notebooklm.generate_audio_review(["http://a"]) == ""


def test_passes_title_into_prompt(monkeypatch):
    got = {}
    monkeypatch.setattr(notebooklm, "_run",
                        lambda urls, prompt, nb_title="": got.update(
                            urls=urls, prompt=prompt, nb_title=nb_title) or "http://nb/1")
    assert notebooklm.generate_audio_review(
        ["http://a"], title="실행 계층으로 이동한다", date_str="26.08.17") == "http://nb/1"
    assert got["urls"] == ["http://a"]
    assert "실행 계층으로 이동한다" in got["prompt"]
    assert got["nb_title"] == "[Daily] 26.08.17 실행 계층으로 이동한다"


def test_no_prompt_without_title(monkeypatch):
    got = {}
    monkeypatch.setattr(notebooklm, "_run",
                        lambda urls, prompt, nb_title="": got.update(
                            prompt=prompt, nb_title=nb_title) or "http://nb/1")
    notebooklm.generate_audio_review(["http://a"])
    assert got["prompt"] == ""
    assert got["nb_title"] == ""


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


# ── 소스 추가 다이얼로그 진입 (빈 노트북은 이미 열려 있다) ──

def test_open_source_dialog_skips_when_already_open():
    """빈 노트북은 ?addSource=true 로 다이얼로그가 열린 채 뜬다.
    그때 '출처 추가' 는 role=button 으로 노출되지 않아 누르면 실패한다."""
    page = MagicMock()
    clicked = []

    def get_by_role(role, name=None, exact=None):
        loc = MagicMock()
        if name in notebooklm._L["website"]:
            loc.first.wait_for.return_value = None
            loc.first.click.side_effect = lambda: clicked.append(name)
        else:
            loc.first.wait_for.side_effect = RuntimeError("not found")
        return loc

    page.get_by_role.side_effect = get_by_role
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._open_source_dialog(page) is True
    assert clicked and clicked[0] in notebooklm._L["website"]


def test_open_source_dialog_clicks_add_when_closed():
    """소스가 이미 있는 노트북은 다이얼로그가 닫혀 있어 '출처 추가' 를 눌러야 한다"""
    page = MagicMock()
    clicked = []
    state = {"dialog_open": False}

    def get_by_role(role, name=None, exact=None):
        loc = MagicMock()
        if name in notebooklm._L["add_source"]:
            loc.first.wait_for.return_value = None
            def _click():
                clicked.append(name)
                state["dialog_open"] = True
            loc.first.click.side_effect = _click
        elif name in notebooklm._L["website"] and state["dialog_open"]:
            loc.first.wait_for.return_value = None
            loc.first.click.side_effect = lambda: clicked.append(name)
        else:
            loc.first.wait_for.side_effect = RuntimeError("not found")
        return loc

    page.get_by_role.side_effect = get_by_role
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._open_source_dialog(page) is True
    assert clicked[0] in notebooklm._L["add_source"]
    assert clicked[1] in notebooklm._L["website"]


def test_open_source_dialog_fails_when_nothing_found():
    page = MagicMock()
    page.get_by_role.return_value.first.wait_for.side_effect = RuntimeError("no")
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._open_source_dialog(page) is False


def test_visible_any_detects_present_label():
    page = MagicMock()
    page.get_by_role.return_value.first.wait_for.return_value = None
    assert notebooklm._visible_any(page, ["웹사이트"], timeout=100) is True


def test_visible_any_false_when_absent():
    page = MagicMock()
    page.get_by_role.return_value.first.wait_for.side_effect = RuntimeError("no")
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("no")
    assert notebooklm._visible_any(page, ["없음"], timeout=100) is False


# ── 노트북 생성 + 제목 ──

def test_notebook_title_format():
    """[Daily] YY.MM.DD 제목 형식"""
    assert notebooklm._notebook_title("26.08.17", "실행 계층으로 이동한다") == \
        "[Daily] 26.08.17 실행 계층으로 이동한다"


def test_notebook_title_without_headline():
    assert notebooklm._notebook_title("26.08.17", "") == "[Daily] 26.08.17"


def test_notebook_title_truncates_long_headline():
    long = "가" * 200
    t = notebooklm._notebook_title("26.08.17", long)
    assert len(t) <= 80
    assert t.startswith("[Daily] 26.08.17 ")
    assert t.endswith("…")


def test_notebook_title_strips_newlines():
    t = notebooklm._notebook_title("26.08.17", "첫 줄\n둘째 줄")
    assert "\n" not in t
    assert "첫 줄 둘째 줄" in t


def test_set_title_fills_first_textbox():
    page = MagicMock()
    box = MagicMock()
    box.input_value.return_value = "[Daily] 26.08.17 제목"
    page.get_by_role.return_value.first = box
    assert notebooklm._set_title(page, "[Daily] 26.08.17 제목") is True
    box.fill.assert_called_once_with("[Daily] 26.08.17 제목")


def test_set_title_retries_when_overwritten():
    """소스를 넣으면 Gemini 가 자동 제목으로 덮어쓴다 — 반영 여부를 값으로 확인해야 한다"""
    page = MagicMock()
    box = MagicMock()
    box.input_value.side_effect = ["Gemini 가 지은 제목", "[Daily] 26.08.17 제목"]
    page.get_by_role.return_value.first = box
    assert notebooklm._set_title(page, "[Daily] 26.08.17 제목") is True
    assert box.fill.call_count == 2


def test_set_title_gives_up_after_retries():
    page = MagicMock()
    box = MagicMock()
    box.input_value.return_value = "계속 덮어써짐"
    page.get_by_role.return_value.first = box
    assert notebooklm._set_title(page, "[Daily] 26.08.17 제목", retries=2) is False
    assert box.fill.call_count == 2


def test_set_title_returns_false_on_failure():
    page = MagicMock()
    page.get_by_role.return_value.first.fill.side_effect = RuntimeError("no")
    assert notebooklm._set_title(page, "제목") is False


def test_set_title_skips_empty():
    page = MagicMock()
    assert notebooklm._set_title(page, "") is False
    page.get_by_role.assert_not_called()
