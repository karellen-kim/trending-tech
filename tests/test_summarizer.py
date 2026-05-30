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
