import json
from unittest.mock import patch

import digest as weekly


def test_load_day_prefers_json(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    (tmp_path / "2026-08-19.json").write_text(json.dumps({
        "date": "2026-08-19",
        "today_take": {"headline": "JSON 헤드라인", "body": "본문"},
        "important_links": [{"text": "글1", "url": "http://a"}],
    }, ensure_ascii=False), encoding="utf-8")
    d = weekly.load_day("2026-08-19")
    assert d["headline"] == "JSON 헤드라인"
    assert d["links"][0]["url"] == "http://a"


def test_load_day_falls_back_to_html(tmp_path, monkeypatch):
    """예전 페이지에는 JSON 필드가 없어 HTML 에서 읽어야 한다"""
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    (tmp_path / "2026-08-17.json").write_text('{"date": "2026-08-17"}', encoding="utf-8")
    (tmp_path / "2026-08-17.html").write_text(
        '<p class="take-headline">HTML 헤드라인</p>'
        '<p class="take-body">HTML 본문</p>'
        '<div class="item important"><details><summary>'
        '<span class="item-name"><span class="item-star">★</span>중요한 글</span></summary>'
        '<div class="item-link"><a href="http://b" target="_blank">중요한 글</a></div>'
        '</details></div>', encoding="utf-8")
    d = weekly.load_day("2026-08-17")
    assert d["headline"] == "HTML 헤드라인"
    assert d["body"] == "HTML 본문"
    assert d["links"] and d["links"][0]["url"] == "http://b"
    assert "중요한 글" in d["links"][0]["text"]


def test_load_day_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    assert weekly.load_day("2026-01-01") == {}


def test_load_week_collects_days(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    for d, h in (("2026-08-17", "월요일 해석"), ("2026-08-19", "수요일 해석")):
        (tmp_path / f"{d}.json").write_text(json.dumps({
            "date": d, "today_take": {"headline": h, "body": ""},
            "important_links": [{"text": f"{d} 글", "url": f"http://{d}"}],
        }, ensure_ascii=False), encoding="utf-8")
    days = weekly.load_week([{"date": "2026-08-17"}, {"date": "2026-08-19"},
                             {"date": "2026-08-20"}])
    assert len(days) == 2, "데이터 없는 날은 빠져야 한다"
    assert days[0]["headline"] == "월요일 해석"


def test_load_month_collects_weeks(tmp_path, monkeypatch):
    """월간 해석은 주간 해석들을 모아 만든다"""
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    import json
    for wid, h in (("2026-W33", "33주 해석"), ("2026-W34", "34주 해석")):
        (tmp_path / f"{wid}.json").write_text(json.dumps({
            "week_id": wid, "week_label": f"{wid} 라벨",
            "days": [{"date": "2026-08-17"}],
            "week_take": {"headline": h, "body": "",
                          "picks": [{"text": f"{wid} 글", "url": f"http://{wid}", "why": "w"}]},
        }, ensure_ascii=False), encoding="utf-8")
    weeks = weekly.load_month(2026, 8)
    got = [w["headline"] for w in weeks]
    assert "33주 해석" in got and "34주 해석" in got


def test_load_month_skips_weeks_without_take(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "DOCS_DIR", tmp_path)
    import json
    (tmp_path / "2026-W33.json").write_text(json.dumps({
        "week_id": "2026-W33", "days": [{"date": "2026-08-10"}]}), encoding="utf-8")
    assert weekly.load_month(2026, 8) == []


def test_month_id_and_label():
    assert weekly.month_id(2026, 8) == "2026-08"
    assert "2026년 8월" in weekly.month_label("2026-08")
