import json
import os
import re
import signal
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from uuid import uuid4

from config import COLLECT_DAYS, LOGS_DIR

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

LLM_TIMEOUT = 600
_LLM_LOCK = Lock()
_ACTIVE_CALLS = 0


class LlmCallError(RuntimeError):
    """필수 분석에 쓸 수 없는 LLM 결과를 실패 종류와 항목 문맥으로 전달한다."""

    def __init__(self, kind: str, message: str, context: str = ""):
        self.kind = kind
        self.context = _redact_cli_error(context)[:200]
        message = _redact_cli_error(message)
        self.message = message
        super().__init__(f"{kind}: {message}" + (f" ({self.context})" if self.context else ""))


def _redact_cli_error(text: str) -> str:
    """진단에 필요한 오류만 남기고 자격 증명·이메일을 제거한다."""
    text = re.sub(r"(?i)\b(bearer|basic)\s+[^\s\"']+", r"\1 [redacted]", text)
    text = re.sub(r"\b(?:xox[baprs]-[\w-]+|sk-[\w-]+|eyJ[\w-]+\.[\w-]+\.[\w-]+)", "[redacted]", text)
    text = re.sub(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted]", text)
    text = re.sub(
        r'''(?i)(["']?(?:access[_-]?token|refresh[_-]?token|token|api[_-]?key|authorization|password|secret)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,&]+)''',
        r'\1"[redacted]"', text,
    )
    return text[-1500:]


def _log_llm_event(event: str, **fields) -> None:
    """프롬프트·응답 본문 없이 호출 상태를 콘솔과 배치 진단 파일에 기록한다."""
    record = json.dumps({"event": event, "time": datetime.now(timezone.utc).isoformat(), "process_id": os.getpid(), **fields}, ensure_ascii=False)
    with _LLM_LOCK:
        print(record, flush=True)
        try:
            LOGS_DIR.mkdir(exist_ok=True)
            with (LOGS_DIR / "llm-calls.log").open("a", encoding="utf-8") as log:
                log.write(record + "\n")
        except OSError:
            pass


def _run_codex(prompt: str, timeout: int = LLM_TIMEOUT, *, strict: bool = False,
               context: str = "llm") -> str:
    """Codex 최종 응답을 읽고 필수 호출의 실패는 명시적인 예외로 전달한다."""
    global _ACTIVE_CALLS
    prompt = prompt.replace("\x00", "")
    context = _redact_cli_error(context)[:200]
    call_id = uuid4().hex[:12]
    start = monotonic()
    with _LLM_LOCK:
        _ACTIVE_CALLS += 1
        active_calls = _ACTIVE_CALLS
    _log_llm_event("llm_call_started", call_id=call_id, context=context,
                   timeout_seconds=timeout, input_chars=len(prompt), active_calls=active_calls)
    status, error, stderr = "cancelled", "", ""
    try:
        with TemporaryDirectory(prefix="trending-codex-") as temp_dir:
            output_path = Path(temp_dir) / "response.txt"
            process = subprocess.Popen(
                ["codex", "exec", "--model", "gpt-6.1-sol", "--json",
                 "--sandbox", "read-only", "--ephemeral", "--color", "never",
                 "--output-last-message", str(output_path), "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
            try:
                _, stderr = process.communicate(input=prompt, timeout=timeout)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, stderr = process.communicate()
                raise
            if process.returncode != 0:
                raise LlmCallError("process_error", f"exit={process.returncode}; {_redact_cli_error(stderr)}", context)
            result = output_path.read_text(encoding="utf-8").strip()
            if not result:
                raise LlmCallError("empty_response", "최종 응답이 비어 있습니다", context)
            status = "success"
            return result
    except subprocess.TimeoutExpired:
        status, error = "timeout", f"{timeout}초 안에 호출이 완료되지 않았습니다"
        if stderr:
            error += "; " + _redact_cli_error(stderr)
        if strict:
            raise LlmCallError(status, error, context) from None
        return ""
    except (LlmCallError, OSError, ValueError) as exc:
        status = exc.kind if isinstance(exc, LlmCallError) else "execution_error"
        error = _redact_cli_error(str(exc))
        if strict:
            if isinstance(exc, LlmCallError):
                raise
            raise LlmCallError(status, error, context) from None
        return ""
    finally:
        with _LLM_LOCK:
            _ACTIVE_CALLS -= 1
            remaining_calls = _ACTIVE_CALLS
        _log_llm_event("llm_call_finished", call_id=call_id, context=context, status=status,
                       elapsed_seconds=round(monotonic() - start, 3), active_calls=remaining_calls, error=error)

def translate_title(title: str) -> str:
    if not title or not title.strip():
        return title
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / max(len(title), 1)
    if ascii_ratio < 0.6:
        return title
    return _run_codex(TRANSLATE_TITLE_PROMPT.format(title=title), timeout=LLM_TIMEOUT, context=f"translate:{title}")

def summarize_item(title: str, content: str) -> str:
    if not content or len(content.strip()) < 150:
        return ""
    return _run_codex(SUMMARIZE_PROMPT.format(title=title, content=content[:2000]), context=f"summarize:{title}")

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
    """제목 번역 + 핵심 요약을 Codex 호출 한 번으로 처리한다.
    date_verified=False(피드에서 날짜를 못 읽은 경우)일 때만 날짜 판정까지 함께 시킨다."""
    content = (content or "")[:1500]
    if date_verified:
        raw = _run_codex(SUMMARIZE_ONLY_PROMPT.format(title=title, content=content), timeout=LLM_TIMEOUT,
                         strict=True, context=f"analyze:{title}")
        parsed = _parse_json(raw)
        if not isinstance(parsed, dict) or not all(isinstance(parsed.get(k), str) for k in ("title_ko", "summary")):
            raise LlmCallError("invalid_response", "분석 JSON 응답이 아닙니다", title)
        return {
            "is_today": True,
            "pub_date": "",
            "title_ko": str(parsed.get("title_ko") or ""),
            "summary": str(parsed.get("summary") or ""),
        }

    raw = _run_codex(ANALYZE_PROMPT.format(
        today=today, recent_desc=_recent_desc(today, days),
        pub_hint=pub_hint or "unknown",
        title=title, content=content), timeout=LLM_TIMEOUT, strict=True, context=f"analyze:{title}")
    data = _parse_json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("is_today"), bool):
        raise LlmCallError("invalid_response", "is_today는 명시적인 bool이어야 합니다", title)
    if data["is_today"] and not all(isinstance(data.get(k), str) for k in ("title_ko", "summary")):
        raise LlmCallError("invalid_response", "번역·요약 필드는 문자열이어야 합니다", title)
    return {
        "is_today": data["is_today"],
        "pub_date": str(data.get("pub_date") or "unknown"),
        "title_ko": str(data.get("title_ko") or ""),
        "summary": str(data.get("summary") or ""),
    }

HIGHLIGHT_PROMPT = """오늘의 개발/기술 트렌드 항목들을 보고, 가장 중요하고 임팩트 있는 것 5개를 골라서
각각 한국어로 한 줄(50자 이내)로 요약해줘.
형식: 각 줄에 하나씩, 번호 없이, 글머리 기호 없이.

{items_text}"""

TAKE_TIMEOUT = LLM_TIMEOUT

TODAY_TAKE_PROMPT = """아래는 오늘 수집된 기술 글 목록이야.
개별 글을 요약하지 말고, 이 글들을 가로질러 읽었을 때 드러나는 흐름 하나를 짚어줘.

{items_text}

JSON만 출력해. 마크다운 펜스나 설명 없이.
{{"headline": "", "body": "", "refs": [1, 2, 3]}}

규칙:
- headline: 한 문장(90자 이내). 무엇이 어디에서 어디로 움직이는지, 또는 무엇이 새로 문제가
  되기 시작했는지를 구체적으로 써.
  "AI가 빠르게 발전하고 있다", "다양한 기술이 등장했다" 같은 하나마나 한 문장은 실패다.
  이 목록을 안 본 사람이 읽고 "그래서 뭐가 달라졌는데?"라고 되물으면 실패다.
- body: 왜 그렇게 보는지 2~3문장. 어떤 글의 어떤 내용이 그 근거인지 짚어줘.
  글 제목을 나열하지 말고 내용으로 설명해.
- refs: headline 의 근거가 된 항목 번호 3~5개. 중요한 순서대로.
- 목록에 있는 내용만 근거로 써. 없는 사실을 지어내지 마.
- 오늘 글들이 서로 무관하면 억지로 엮지 말고 가장 굵은 줄기 하나만 짚어.
"""

PERIOD_TAKE_PROMPT = """아래는 {period_desc} 동안의 {unit}별 해석과 그때 꼽힌 문서들이야.

{items_text}

{unit}별 해석을 나열하지 말고, {period_desc} 전체를 관통하는 흐름 하나를 짚어줘.
그리고 위 문서 중 {period_desc}을 통틀어 가장 중요한 것 {pick_n}건을 골라줘.

JSON만 출력해. 마크다운 펜스나 설명 없이.
{{"headline": "", "body": "", "picks": [{{"text": "", "url": "", "why": ""}}]}}

규칙:
- headline: 한 문장(90자 이내). {period_desc} 사이에 무엇이 어디로 움직였는지 구체적으로.
  "AI가 발전했다" 같은 하나마나 한 문장은 실패다.
  {unit}별 해석을 이어 붙인 요약도 실패다. 그것들을 관통하는 한 줄이어야 한다.
- body: 왜 그렇게 보는지 2~4문장. 어느 {unit}의 어떤 내용이 근거인지 짚어줘.
- picks: 위 목록에 실제로 있는 문서만 고른다. text 와 url 은 목록에 있는 것을 그대로 옮겨 쓴다.
  why 는 왜 중요한지 한 줄(40자 이내).
- 목록에 없는 문서나 URL 을 지어내면 실패다.
"""

HIGHLIGHT_LINK_PROMPT = """오늘의 개발/기술 트렌드 항목 목록이야.
가장 중요하고 임팩트 있는 것 5개를 골라줘.

형식: 각 줄에 "번호|한 줄 요약(50자 이내)" 로만 답해. 다른 말 없이.
예: 3|새 모델이 코딩 벤치마크에서 기존 대비 크게 앞섰다

{items_text}"""


def _highlight_candidates(data: dict) -> list[dict]:
    items = []
    for key, tag in (("company_blogs", ""), ("dev_blogs", ""),
                     ("papers", "논문"), ("github", "GitHub")):
        for i in data.get(key, []):
            title = i.get("title_ko") or i.get("title") or i.get("name", "")
            if not title:
                continue
            items.append({"title": title, "url": i.get("url", ""),
                          "source": tag or i.get("source", "")})
    return items[:20]


def generate_today_take(data: dict) -> dict:
    """오늘 글들을 가로질러 읽은 해석 한 문장과 그 근거를 만든다.
    반환: {"headline", "body", "refs": [{"text","url","source"}]}
    refs 는 근거가 된 글이며, 목록에서 ★ 로 표시된다. 실패하면 빈 dict."""
    cands = _highlight_candidates(data)
    if not cands:
        return {}
    items_text = "\n".join(f"{n + 1}. [{c['source']}] {c['title']}" for n, c in enumerate(cands))
    prompt = TODAY_TAKE_PROMPT.format(items_text=items_text)

    # 항목 20건을 한 번에 처리하므로 개별 글 요약보다 오래 걸린다.
    # 실패하면 페이지에서 해석과 별표가 통째로 빠지므로 한 번 재시도한다.
    parsed, headline = None, ""
    for attempt in range(2):
        parsed = _parse_json(_run_codex(prompt, timeout=TAKE_TIMEOUT, context="today_take"))
        headline = str((parsed or {}).get("headline") or "").strip() if isinstance(parsed, dict) else ""
        if headline:
            break
        if attempt == 0:
            print("[해석] 생성 실패, 재시도")
    if not headline:
        return {}

    refs, seen = [], set()
    for r in (parsed.get("refs") or []):
        try:
            idx = int(r) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < len(cands) or idx in seen:
            continue
        seen.add(idx)
        refs.append(dict(cands[idx]))
        if len(refs) >= 5:
            break

    return {"headline": headline,
            "body": str(parsed.get("body") or "").strip(),
            "refs": [{"text": r["title"], "url": r["url"], "source": r["source"]} for r in refs]}


def mark_important(data: dict, refs: list[dict]) -> None:
    """해석의 근거가 된 글에 important 플래그를 세운다. 렌더러가 ★ 로 표시한다."""
    urls = {r.get("url") for r in refs if r.get("url")}
    if not urls:
        return
    for key in ("company_blogs", "dev_blogs", "papers", "github"):
        for i in data.get(key, []):
            if i.get("url") in urls:
                i["important"] = True


def generate_highlight_links(data: dict) -> list[dict]:
    """하이라이트 문장과 원문 링크를 함께 돌려준다.
    기존 generate_highlights 는 문장만 주어 어느 글에서 나왔는지 알 수 없었다."""
    cands = _highlight_candidates(data)
    if not cands:
        return []
    items_text = "\n".join(f"{n + 1}. [{c['source']}] {c['title']}" for n, c in enumerate(cands))
    response = _run_codex(HIGHLIGHT_LINK_PROMPT.format(items_text=items_text), timeout=LLM_TIMEOUT, context="highlight_links")
    out, seen = [], set()
    for line in (response or "").splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        num, _, text = line.partition("|")
        num = num.strip().lstrip("0") or "0"
        if not num.isdigit():
            continue
        idx = int(num) - 1
        if not 0 <= idx < len(cands) or not text.strip() or idx in seen:
            continue
        seen.add(idx)
        c = cands[idx]
        out.append({"text": text.strip(), "url": c["url"], "source": c["source"]})
        if len(out) >= 5:
            break
    return out


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
    response = _run_codex(HIGHLIGHT_PROMPT.format(items_text=items_text), timeout=LLM_TIMEOUT, context="highlights")
    return [line.strip() for line in response.splitlines() if line.strip()][:5]

def filter_important_papers(papers: list[dict], max_items: int = 5) -> list[dict]:
    if not papers:
        return []
    papers_list = "\n".join(
        f"{i+1}. {p['title']}: {p['abstract'][:200]}"
        for i, p in enumerate(papers)
    )
    response = _run_codex(FILTER_PROMPT.format(max_items=max_items, papers_list=papers_list), timeout=LLM_TIMEOUT, strict=True, context="paper_selection")
    if not re.fullmatch(r"\s*\d+(?:\s*,\s*\d+)*\s*", response):
        raise LlmCallError("invalid_response", "논문 선택 응답은 번호 목록이어야 합니다", "paper_selection")
    indices = list(dict.fromkeys(int(value.strip()) - 1 for value in response.split(",")))
    if not all(0 <= index < len(papers) for index in indices):
        raise LlmCallError("invalid_response", "논문 선택 번호가 범위를 벗어났습니다", "paper_selection")
    return [papers[index] for index in indices[:max_items]]


def _period_take(entries: list[dict], period_desc: str, unit: str, pick_n: int = 4) -> dict:
    """기간 해석과 대표 문서를 만든다. 주간·월간이 같은 로직을 쓴다.
    반환: {"headline", "body", "picks": [{"text","url","why"}]}"""
    entries = [e for e in entries if e.get("headline")]
    if not entries:
        return {}

    lines, allowed = [], {}
    for e in entries:
        lines.append(f"[{e.get('date','')}] {e['headline']}")
        for l in e.get("links", []):
            url = l.get("url", "")
            if not url:
                continue
            allowed[url] = l.get("text", "")
            lines.append(f"    - {l.get('text','')} :: {url}")
    if not allowed:
        return {}

    prompt = PERIOD_TAKE_PROMPT.format(
        period_desc=period_desc, unit=unit, pick_n=pick_n,
        items_text="\n".join(lines))
    parsed, headline = None, ""
    for attempt in range(2):
        parsed = _parse_json(_run_codex(prompt, timeout=TAKE_TIMEOUT, context="period_take"))
        headline = str((parsed or {}).get("headline") or "").strip() if isinstance(parsed, dict) else ""
        if headline:
            break
        if attempt == 0:
            print(f"[{unit} 해석] 생성 실패, 재시도")
    if not headline:
        return {}

    picks, seen = [], set()
    for p in (parsed.get("picks") or []):
        if not isinstance(p, dict):
            continue
        url = str(p.get("url") or "").strip()
        # 목록에 없는 URL 을 지어내는 경우가 있어 걸러낸다
        if url not in allowed or url in seen:
            continue
        seen.add(url)
        picks.append({"text": str(p.get("text") or allowed[url]),
                      "url": url,
                      "why": str(p.get("why") or "")})
        if len(picks) >= pick_n:
            break

    return {"headline": headline,
            "body": str(parsed.get("body") or "").strip(),
            "picks": picks}


def generate_week_take(days: list[dict], pick_n: int = 4) -> dict:
    """일별 해석들을 모아 이 주의 해석과 대표 문서를 만든다."""
    return _period_take(days, "이번 주", "일", pick_n)


def generate_month_take(weeks: list[dict], pick_n: int = 4) -> dict:
    """주간 해석들을 모아 이 달의 해석과 대표 문서를 만든다."""
    return _period_take(weeks, "이번 달", "주", pick_n)
