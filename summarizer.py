import subprocess

TRANSLATE_TITLE_PROMPT = """다음 영어 제목을 자연스러운 한국어로 번역해줘.
규칙: 번역문만 출력해. 설명, 부연, 따옴표 없이.
고유명사(제품명, 회사명, 기술명)는 그대로 유지해.

제목: {title}
번역:"""

SUMMARIZE_PROMPT = """아래 [내용]을 한국어로 3~5줄로 요약해줘.
규칙: 반드시 [내용]에 있는 정보만 사용해. 추가 지식이나 추론으로 내용을 만들어내지 마.
내용이 불충분하면 빈 문자열만 반환해.

제목: {title}
[내용]: {content}
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

def translate_title(title: str) -> str:
    if not title or not title.strip():
        return title
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / max(len(title), 1)
    if ascii_ratio < 0.6:
        return title
    return _run_claude(TRANSLATE_TITLE_PROMPT.format(title=title), timeout=30)

def summarize_item(title: str, content: str) -> str:
    if not content or len(content.strip()) < 150:
        return ""
    return _run_claude(SUMMARIZE_PROMPT.format(title=title, content=content[:2000]))

HIGHLIGHT_PROMPT = """오늘의 개발/기술 트렌드 항목들을 보고, 가장 중요하고 임팩트 있는 것 5개를 골라서
각각 한국어로 한 줄(50자 이내)로 요약해줘.
형식: 각 줄에 하나씩, 번호 없이, 글머리 기호 없이.

{items_text}"""

def generate_highlights(data: dict) -> list[str]:
    items = []
    for i in data.get("company_blogs", [])[:3]:
        items.append(f"[{i.get('source','')}] {i.get('title','')}")
    for i in data.get("dev_blogs", [])[:3]:
        items.append(f"[{i.get('source','')}] {i.get('title','')}")
    for i in data.get("papers", [])[:3]:
        items.append(f"[논문] {i.get('title','')}")
    for i in data.get("hn", [])[:3]:
        items.append(f"[HN] {i.get('title','')}")
    for i in data.get("reddit", [])[:3]:
        items.append(f"[Reddit/{i.get('source','')}] {i.get('title','')}")
    for i in data.get("github", [])[:3]:
        items.append(f"[GitHub] {i.get('name','')}: {i.get('description','')[:60]}")
    if not items:
        return []
    items_text = "\n".join(items[:20])
    response = _run_claude(HIGHLIGHT_PROMPT.format(items_text=items_text), timeout=90)
    return [line.strip() for line in response.splitlines() if line.strip()][:5]

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
