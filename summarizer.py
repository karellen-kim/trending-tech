import json
import re
import subprocess
from datetime import datetime, timedelta

from config import COLLECT_DAYS

SUMMARIZE_ONLY_PROMPT = """아래 글의 제목을 한국어로 옮기고 핵심을 정리해줘.

[제목]: {title}
[내용]: {content}

아래 JSON 형식으로만 답해. 설명이나 마크다운 없이 JSON만.
{{"title_ko": "", "summary": ""}}

규칙:
- title_ko: 제목을 자연스러운 한국어로. 고유명사(제품명·회사명·기술명)는 그대로 유지해.
  제목이 이미 한국어면 그대로 써.
- summary: 첫 줄에 무엇에 관한 글인지 한 줄, 그 다음 핵심 3가지를 각각 "- "로 시작하는 줄로.
  반드시 [내용]에 있는 정보만 사용해. 추가 지식이나 추론으로 만들어내지 마.
  배경 설명·일반론은 빼고 이 글에만 있는 구체적인 사실·수치·기법을 골라.
  [내용]이 불충분하면 빈 문자열.
"""

ANALYZE_PROMPT = """오늘은 {today} (KST)야.
아래 글이 최근 글({recent_desc})인지 판단하고, 맞으면 제목을 번역하고 핵심을 정리해줘.

[발행일 정보]: {pub_hint}
[제목]: {title}
[내용]: {content}

아래 JSON 형식으로만 답해. 설명이나 마크다운 없이 JSON만.
{{"is_today": true 또는 false, "pub_date": "YYYY-MM-DD 또는 unknown", "title_ko": "", "summary": ""}}

규칙:
- [발행일 정보]가 {recent_desc} 중 하나면 is_today 는 true. 그보다 오래됐거나 미래면 false.
- [발행일 정보]가 unknown 이면 [내용]에서 발행일을 찾아봐. 그래도 확인 안 되면 false.
- is_today 가 false 면 title_ko 와 summary 는 빈 문자열로 두고 끝내.
- title_ko: 제목을 자연스러운 한국어로. 고유명사(제품명·회사명·기술명)는 그대로 유지해.
  제목이 이미 한국어면 그대로 써.
- summary: 첫 줄에 무엇에 관한 글인지 한 줄, 그 다음 핵심 3가지를 각각 "- "로 시작하는 줄로.
  반드시 [내용]에 있는 정보만 사용해. 추가 지식이나 추론으로 만들어내지 마.
  배경 설명·일반론은 빼고 이 글에만 있는 구체적인 사실·수치·기법을 골라.
  [내용]이 불충분하면 빈 문자열.
"""

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

def _run_claude(prompt: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            print(f"[claude] 실패(rc={result.returncode}): {result.stderr.strip()[:200]}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"[claude] 타임아웃({timeout}s)")
        return ""

def translate_title(title: str) -> str:
    if not title or not title.strip():
        return title
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / max(len(title), 1)
    if ascii_ratio < 0.6:
        return title
    return _run_claude(TRANSLATE_TITLE_PROMPT.format(title=title), timeout=60)

def summarize_item(title: str, content: str) -> str:
    if not content or len(content.strip()) < 150:
        return ""
    return _run_claude(SUMMARIZE_PROMPT.format(title=title, content=content[:2000]))

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_JSON_OBJ = re.compile(r"\{.*\}", re.S)
_SAFE_DEFAULT = {"is_today": False, "pub_date": "unknown", "title_ko": "", "summary": ""}

def _parse_json(raw: str) -> dict | None:
    """모델 응답에서 JSON 오브젝트를 뽑는다. 실패하면 None."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    m = _JSON_OBJ.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

def _recent_desc(today: str, days: int) -> str:
    d = datetime.strptime(today, "%Y-%m-%d").date()
    return " 또는 ".join(str(d - timedelta(days=i)) for i in range(days))

def analyze_item(title: str, content: str, pub_hint: str, today: str,
                 date_verified: bool = False, days: int = COLLECT_DAYS) -> dict:
    """제목 번역 + 핵심 요약을 claude 호출 한 번으로 처리한다.
    date_verified=False(피드에서 날짜를 못 읽은 경우)일 때만 날짜 판정까지 함께 시킨다."""
    content = (content or "")[:1500]
    if date_verified:
        raw = _run_claude(SUMMARIZE_ONLY_PROMPT.format(title=title, content=content), timeout=120)
        parsed = _parse_json(raw)
        if parsed is None:
            return dict(_SAFE_DEFAULT, is_today=True)
        return {
            "is_today": True,
            "pub_date": "",
            "title_ko": str(parsed.get("title_ko") or ""),
            "summary": str(parsed.get("summary") or ""),
        }

    raw = _run_claude(ANALYZE_PROMPT.format(
        today=today, recent_desc=_recent_desc(today, days),
        pub_hint=pub_hint or "unknown",
        title=title, content=content), timeout=120)
    data = _parse_json(raw)
    if data is None:
        return dict(_SAFE_DEFAULT)
    return {
        "is_today": bool(data.get("is_today")),
        "pub_date": str(data.get("pub_date") or "unknown"),
        "title_ko": str(data.get("title_ko") or ""),
        "summary": str(data.get("summary") or ""),
    }

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
