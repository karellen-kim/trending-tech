from notifier import _build_text


def test_slack_uses_take_when_available():
    take = {"headline": "실행 계층으로 이동한다", "body": "근거다.",
            "refs": [{"text": "글1", "url": "http://a"}]}
    text = _build_text("2026-08-14", take, ["옛날 하이라이트"])
    assert "실행 계층으로 이동한다" in text
    assert "근거다." in text
    assert "<http://a|글1>" in text
    assert "옛날 하이라이트" not in text


def test_slack_falls_back_to_highlights():
    text = _build_text("2026-08-14", None, ["첫째", "둘째"])
    assert "• 첫째" in text and "• 둘째" in text


def test_slack_always_includes_page_link():
    for take in (None, {"headline": "H"}):
        text = _build_text("2026-08-14", take, ["x"])
        assert "https://karellen-kim.github.io/trending-tech/2026-08-14.html" in text


def test_slack_handles_ref_without_url():
    take = {"headline": "H", "refs": [{"text": "링크없음"}]}
    text = _build_text("2026-08-14", take, [])
    assert "• 링크없음" in text
