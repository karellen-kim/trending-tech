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


# ── 하이라이트 ↔ 원문 링크 매핑 ──

def test_highlight_links_map_back_to_urls():
    data = {
        "company_blogs": [{"source": "A", "title": "글1", "url": "http://a"},
                          {"source": "B", "title": "글2", "url": "http://b"}],
        "dev_blogs": [], "papers": [], "github": [],
    }
    with patch("summarizer._run_claude", return_value="2|두 번째가 중요\n1|첫 번째도"):
        links = summarizer.generate_highlight_links(data)
    assert [l["url"] for l in links] == ["http://b", "http://a"]
    assert links[0]["text"] == "두 번째가 중요"


def test_highlight_links_ignores_out_of_range_index():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    with patch("summarizer._run_claude", return_value="9|없는 번호\n1|정상"):
        links = summarizer.generate_highlight_links(data)
    assert len(links) == 1 and links[0]["url"] == "http://a"


def test_highlight_links_survives_unnumbered_output():
    """모델이 번호를 빼먹어도 빈 리스트를 돌려주고 배치는 계속되어야 한다"""
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    with patch("summarizer._run_claude", return_value="번호 없는 줄\n또 한 줄"):
        assert summarizer.generate_highlight_links(data) == []


def test_highlight_links_dedupes_same_index():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"},
                              {"source": "B", "title": "글2", "url": "http://b"}],
            "dev_blogs": [], "papers": [], "github": []}
    with patch("summarizer._run_claude", return_value="1|첫째\n1|또 첫째\n2|둘째"):
        links = summarizer.generate_highlight_links(data)
    assert [l["url"] for l in links] == ["http://a", "http://b"]


def test_highlight_links_empty_when_no_items():
    assert summarizer.generate_highlight_links({}) == []


def test_highlight_candidates_prefer_korean_title():
    data = {"company_blogs": [{"source": "A", "title": "English", "title_ko": "한글제목",
                               "url": "http://a"}], "dev_blogs": [], "papers": [], "github": []}
    cands = summarizer._highlight_candidates(data)
    assert cands[0]["title"] == "한글제목"


# ── 오늘의 해석 ──

def test_today_take_parses_headline_body_refs():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"},
                              {"source": "B", "title": "글2", "url": "http://b"},
                              {"source": "C", "title": "글3", "url": "http://c"}],
            "dev_blogs": [], "papers": [], "github": []}
    payload = ('{"headline": "실행 계층으로 경쟁력이 이동한다",'
               ' "body": "근거 설명이다.", "refs": [2, 3]}')
    with patch("summarizer._run_claude", return_value=payload):
        take = summarizer.generate_today_take(data)
    assert take["headline"] == "실행 계층으로 경쟁력이 이동한다"
    assert take["body"] == "근거 설명이다."
    assert [r["url"] for r in take["refs"]] == ["http://b", "http://c"]


def test_today_take_empty_when_no_headline():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    with patch("summarizer._run_claude", return_value='{"headline": "", "refs": [1]}'):
        assert summarizer.generate_today_take(data) == {}


def test_today_take_empty_on_garbage():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    with patch("summarizer._run_claude", return_value="그냥 문장"):
        assert summarizer.generate_today_take(data) == {}


def test_today_take_ignores_bad_refs():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    payload = '{"headline": "H", "body": "B", "refs": [99, "x", 1, 1]}'
    with patch("summarizer._run_claude", return_value=payload):
        take = summarizer.generate_today_take(data)
    assert [r["url"] for r in take["refs"]] == ["http://a"]


def test_today_take_empty_when_no_items():
    assert summarizer.generate_today_take({}) == {}


def test_mark_important_flags_only_refs():
    data = {"company_blogs": [{"url": "http://a"}, {"url": "http://b"}],
            "dev_blogs": [{"url": "http://c"}], "papers": [], "github": []}
    summarizer.mark_important(data, [{"url": "http://a"}, {"url": "http://c"}])
    assert data["company_blogs"][0].get("important") is True
    assert data["company_blogs"][1].get("important") is None
    assert data["dev_blogs"][0].get("important") is True


def test_mark_important_handles_empty_refs():
    data = {"company_blogs": [{"url": "http://a"}], "dev_blogs": [], "papers": [], "github": []}
    summarizer.mark_important(data, [])
    assert data["company_blogs"][0].get("important") is None


# ── 해석 생성 타임아웃 (8/19 배치에서 120초 초과로 해석·별표가 통째로 빠졌다) ──

def test_today_take_retries_on_empty_response():
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"},
                              {"source": "B", "title": "글2", "url": "http://b"}],
            "dev_blogs": [], "papers": [], "github": []}
    calls = []

    def fake(prompt, timeout=None):
        calls.append(timeout)
        if len(calls) == 1:
            return ""      # 첫 호출 타임아웃
        return '{"headline": "H", "body": "B", "refs": [1]}'

    with patch("summarizer._run_claude", side_effect=fake):
        take = summarizer.generate_today_take(data)
    assert take["headline"] == "H"
    assert len(calls) == 2, "한 번은 재시도해야 한다"


def test_today_take_timeout_is_generous():
    """항목 20건을 한 번에 처리하므로 개별 글 요약보다 넉넉해야 한다"""
    data = {"company_blogs": [{"source": "A", "title": "글1", "url": "http://a"}],
            "dev_blogs": [], "papers": [], "github": []}
    seen = []
    with patch("summarizer._run_claude",
               side_effect=lambda p, timeout=None: seen.append(timeout) or '{"headline":"H","refs":[1]}'):
        summarizer.generate_today_take(data)
    assert seen[0] >= 180, f"타임아웃이 {seen[0]}초로 너무 짧다"


# ── 주간 해석 ──

def test_week_take_parses_headline_and_picks():
    days = [{"date": "2026-08-17", "headline": "월 해석",
             "links": [{"text": "글A", "url": "http://a"}]},
            {"date": "2026-08-19", "headline": "수 해석",
             "links": [{"text": "글B", "url": "http://b"}]}]
    payload = ('{"headline": "이번 주 흐름", "body": "근거다.",'
               ' "picks": [{"text": "글B", "url": "http://b", "why": "핵심이다"}]}')
    with patch("summarizer._run_claude", return_value=payload):
        take = summarizer.generate_week_take(days)
    assert take["headline"] == "이번 주 흐름"
    assert take["picks"][0]["url"] == "http://b"
    assert take["picks"][0]["why"] == "핵심이다"


def test_week_take_drops_picks_not_in_source():
    """목록에 없는 링크를 지어내면 버린다"""
    days = [{"date": "2026-08-17", "headline": "h", "links": [{"text": "글A", "url": "http://a"}]}]
    payload = ('{"headline": "H", "body": "B", "picks": ['
               '{"text": "글A", "url": "http://a", "why": "w"},'
               '{"text": "지어낸 글", "url": "http://fake", "why": "w"}]}')
    with patch("summarizer._run_claude", return_value=payload):
        take = summarizer.generate_week_take(days)
    assert [p["url"] for p in take["picks"]] == ["http://a"]


def test_week_take_limits_to_four():
    links = [{"text": f"글{i}", "url": f"http://{i}"} for i in range(8)]
    days = [{"date": "2026-08-17", "headline": "h", "links": links}]
    picks = ",".join('{"text":"글%d","url":"http://%d","why":"w"}' % (i, i) for i in range(8))
    with patch("summarizer._run_claude", return_value='{"headline":"H","body":"B","picks":[%s]}' % picks):
        take = summarizer.generate_week_take(days)
    assert len(take["picks"]) == 4, "5건 미만이어야 한다"


def test_week_take_empty_without_days():
    assert summarizer.generate_week_take([]) == {}


def test_week_take_empty_on_garbage():
    days = [{"date": "d", "headline": "h", "links": [{"text": "t", "url": "u"}]}]
    with patch("summarizer._run_claude", return_value="딴소리"):
        assert summarizer.generate_week_take(days) == {}


def test_month_take_uses_week_entries():
    weeks = [{"date": "2026-W33", "headline": "33주 흐름",
              "links": [{"text": "글A", "url": "http://a"}]},
             {"date": "2026-W34", "headline": "34주 흐름",
              "links": [{"text": "글B", "url": "http://b"}]}]
    payload = ('{"headline": "이번 달 흐름", "body": "근거",'
               ' "picks": [{"text": "글B", "url": "http://b", "why": "가장 컸다"}]}')
    captured = {}
    def fake(prompt, timeout=None):
        captured["p"] = prompt
        return payload
    with patch("summarizer._run_claude", side_effect=fake):
        take = summarizer.generate_month_take(weeks)
    assert take["headline"] == "이번 달 흐름"
    assert take["picks"][0]["url"] == "http://b"
    assert "주별 해석을 나열하지 말고" in captured["p"] or "주별" in captured["p"]


def test_month_take_empty_without_weeks():
    assert summarizer.generate_month_take([]) == {}
