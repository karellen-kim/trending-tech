import subprocess

SUMMARIZE_PROMPT = """다음 항목을 한국어로 3~5줄 요약해줘. 기술적 핵심만 간결하게.
제목: {title}
내용: {content}
요약:"""

FILTER_PROMPT = """다음 AI/ML 논문 목록에서 오늘 가장 주목할 만한 논문 번호를 최대 {max_items}개 골라줘.
기준: LLM, 에이전트, 추론, 멀티모달, 새로운 아키텍처 등 실용적으로 중요한 것.
번호만 쉼표로 구분해서 답해줘. (예: 1,3,5)

{papers_list}"""

def _run_claude(prompt: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()

def summarize_item(title: str, content: str) -> str:
    return _run_claude(SUMMARIZE_PROMPT.format(title=title, content=content[:2000]))

def filter_important_papers(papers: list[dict], max_items: int = 5) -> list[dict]:
    if not papers:
        return []
    papers_list = "\n".join(
        f"{i+1}. {p['title']}: {p['abstract'][:200]}"
        for i, p in enumerate(papers)
    )
    response = _run_claude(FILTER_PROMPT.format(max_items=max_items, papers_list=papers_list), timeout=90)
    try:
        indices = [int(x.strip()) - 1 for x in response.split(",") if x.strip().isdigit()]
        return [papers[i] for i in indices if 0 <= i < len(papers)]
    except Exception:
        return papers[:max_items]
