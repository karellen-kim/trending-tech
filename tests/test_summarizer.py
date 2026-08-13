from unittest.mock import patch, MagicMock
from summarizer import summarize_item, filter_important_papers

def _mock_proc(stdout="요약 결과입니다.", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m

def test_summarize_item_returns_string():
    long_content = "A small but capable language model by Microsoft. " * 5
    with patch("summarizer.subprocess.run", return_value=_mock_proc()):
        result = summarize_item("phi-4", long_content)
    assert isinstance(result, str)
    assert len(result) > 0

def test_summarize_item_handles_failure():
    with patch("summarizer.subprocess.run", return_value=_mock_proc("", returncode=1)):
        result = summarize_item("title", "content")
    assert result == ""

def test_filter_important_papers_returns_list():
    papers = [
        {"title": "Paper A", "abstract": "About transformers"},
        {"title": "Paper B", "abstract": "About LLM agents"},
        {"title": "Paper C", "abstract": "About image classification"},
    ]
    with patch("summarizer.subprocess.run", return_value=_mock_proc("1,2")):
        result = filter_important_papers(papers, max_items=5)
    assert isinstance(result, list)
    assert len(result) <= len(papers)


# ── 날짜판정 + 제목번역 + 요약 통합 호출 ──

import json
import summarizer


def test_analyze_item_parses_json():
    payload = json.dumps({"is_today": True, "pub_date": "2026-08-14",
                          "title_ko": "한글 제목", "summary": "요약 본문"})
    with patch("summarizer._run_claude", return_value=payload):
        out = summarizer.analyze_item("T", "본문" * 200, "2026-08-14 09:00 KST", "2026-08-14")
    assert out["is_today"] is True
    assert out["title_ko"] == "한글 제목"
    assert out["summary"] == "요약 본문"


def test_analyze_item_handles_code_fence():
    payload = '```json\n{"is_today": false, "pub_date": "2026-07-01", "title_ko": "", "summary": ""}\n```'
    with patch("summarizer._run_claude", return_value=payload):
        out = summarizer.analyze_item("T", "본문" * 200, "2026-07-01", "2026-08-14")
    assert out["is_today"] is False


def test_analyze_item_returns_safe_default_on_garbage():
    with patch("summarizer._run_claude", return_value="모델이 이상한 말을 함"):
        out = summarizer.analyze_item("T", "본문" * 200, "unknown", "2026-08-14")
    assert out == {"is_today": False, "pub_date": "unknown", "title_ko": "", "summary": ""}


def test_analyze_item_calls_llm_once():
    calls = []
    with patch("summarizer._run_claude", side_effect=lambda p, **kw: calls.append(p) or
               '{"is_today": true, "pub_date": "2026-08-14", "title_ko": "x", "summary": "y"}'):
        summarizer.analyze_item("T", "본문" * 200, "2026-08-14", "2026-08-14")
    assert len(calls) == 1, "날짜판정·번역·요약은 한 번의 호출로 처리해야 한다"


def test_analyze_prompt_includes_today_and_hint():
    captured = {}

    def fake(prompt, **kw):
        captured["p"] = prompt
        return '{"is_today": true, "pub_date": "2026-08-14", "title_ko": "x", "summary": "y"}'

    with patch("summarizer._run_claude", side_effect=fake):
        summarizer.analyze_item("T", "본문" * 200, "2026-08-13 10:00 KST", "2026-08-14")
    assert "2026-08-14" in captured["p"]
    assert "2026-08-13 10:00 KST" in captured["p"]
