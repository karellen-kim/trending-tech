# NotebookLM 오디오 리뷰 자동화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 매일 생성되는 하이라이트 5건의 원문 링크를 NotebookLM에 올리고 AI 오디오 리뷰(Audio Overview)를 자동 생성해 `docs/audio/`에 저장한다.

**Architecture:** `notebooklm-podcast-automator`(FastAPI + Playwright)를 별도 프로세스로 띄우고, 이 저장소는 그 REST API를 호출하는 얇은 클라이언트(`notebooklm.py`)만 갖는다. 파이프라인 끝에서 `사전 정리 → 링크 업로드 → 오디오 생성 → 폴링 → 다운로드` 순으로 진행하고, 실패해도 나머지 배치는 그대로 끝나도록 전 구간을 예외 격리한다.

**Tech Stack:** Python 3.10+, requests (이미 의존성에 있음), 외부 서비스 notebooklm-podcast-automator

**Spec:** 이 문서

## Global Constraints

- 새 서드파티 의존성 추가 금지 — `requests`만 쓴다
- `.env` 파일은 수정하지 않는다 (사용자가 직접 넣는다)
- NotebookLM 연동이 실패해도 HTML 생성·커밋·푸시는 정상 완료되어야 한다
- 기본값은 **꺼짐**(`ENABLE_NOTEBOOKLM = False`) — 환경이 준비된 뒤 사용자가 켠다

---

## 외부 도구 조사 결과 (실제 소스 확인)

저장소: https://github.com/israelbls/notebooklm-podcast-automator

**엔드포인트** (`src/notebooklm_automator/api/routes.py`)
```
POST /sources/upload        {"sources": [{"type": "url"|"youtube"|"text", "content": "..."}]}
                            → {"overall_success": bool, "results": [{"source", "success", "error"}]}
POST /sources/clear         → {"success": bool, "count": int}
POST /audio/generate        {"style": ..., "prompt": ..., "language": ...} → {"job_id", "status"}
GET  /audio/status/{job_id} → {"status": "pending|processing|completed|failed", "download_url", "error"}
GET  /audio/file/{job_id}
GET  /audio/download/{job_id}
POST /studio/clear          → {"success": bool, "count": int}
```

**AudioStyle** (`api/models.py`): `summary`, `deep_dive`, `criticism`, `debate`

**인증·실행 요건** (`core/browser.py`, README)
- Chrome 프로필 `~/.notebooklm-chrome` 에 **최초 1회 수동 Google 로그인** 필요
- Chrome 원격 디버깅 포트 9222 (`NOTEBOOKLM_CHROME_PORT`)
- `NOTEBOOKLM_URL` 환경변수로 **기존 노트북 URL**을 지정한다 — 이 도구는 노트북을 새로 만들지 않는다
- 그 외: `NOTEBOOKLM_CHROME_HOST`, `NOTEBOOKLM_CHROME_PATH`, `NOTEBOOKLM_CHROME_USER_DATA_DIR`,
  `NOTEBOOKLM_AUTO_LAUNCH_CHROME`
- headless 지원은 문서에 명시돼 있지 않다. 최초 로그인은 창이 보이는 Chrome 이 필요하다.

**알려진 제약**
- 노트북 하나를 재사용하므로 매일 실행하려면 `sources/clear` 로 먼저 비워야 한다
- 오디오 생성은 수 분 걸린다
- 다운로드는 Chrome 프로필의 다운로드 권한에 의존한다

---

### Task 1: NotebookLM 클라이언트

**Files:**
- Create: `notebooklm.py`
- Test: `tests/test_notebooklm.py`

**Interfaces:**
- Produces: `generate_audio_review(urls, out_path, title="") -> str | None`
  성공 시 저장된 파일 경로, 실패하면 `None`. 예외를 밖으로 던지지 않는다.
- 내부: `_post/_get` 헬퍼, `clear_sources()`, `upload_urls()`, `start_audio()`, `wait_for_audio()`, `download_audio()`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_notebooklm.py
from unittest.mock import patch, Mock
import notebooklm


def _resp(payload, status=200):
    r = Mock(status_code=status)
    r.json = Mock(return_value=payload)
    r.raise_for_status = Mock()
    r.content = b"AUDIO"
    return r


def test_uploads_urls_as_source_objects():
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent[url] = json
        if url.endswith("/sources/clear"):
            return _resp({"success": True, "count": 0})
        if url.endswith("/sources/upload"):
            return _resp({"overall_success": True, "results": []})
        return _resp({"job_id": "j1", "status": "pending"})

    with patch("notebooklm.requests.post", side_effect=fake_post), \
         patch("notebooklm.requests.get", return_value=_resp(
             {"job_id": "j1", "status": "completed", "download_url": "/x"})), \
         patch("notebooklm.open", create=True):
        notebooklm.generate_audio_review(["http://a", "http://b"], "/tmp/x.mp3")

    body = sent["http://127.0.0.1:8000/sources/upload"]
    assert body == {"sources": [{"type": "url", "content": "http://a"},
                                {"type": "url", "content": "http://b"}]}


def test_clears_sources_before_upload():
    order = []

    def fake_post(url, json=None, timeout=None):
        order.append(url.rsplit("/", 2)[-2] + "/" + url.rsplit("/", 1)[-1])
        if "audio" in url:
            return _resp({"job_id": "j1", "status": "pending"})
        return _resp({"success": True, "count": 1, "overall_success": True, "results": []})

    with patch("notebooklm.requests.post", side_effect=fake_post), \
         patch("notebooklm.requests.get", return_value=_resp(
             {"status": "completed", "download_url": "/x"})), \
         patch("notebooklm.open", create=True):
        notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3")

    assert order[0] == "sources/clear", order


def test_returns_none_when_server_unreachable():
    import requests
    with patch("notebooklm.requests.post", side_effect=requests.ConnectionError("no server")):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3") is None


def test_returns_none_on_failed_job():
    with patch("notebooklm.requests.post", return_value=_resp({"job_id": "j", "status": "pending"})), \
         patch("notebooklm.requests.get", return_value=_resp(
             {"status": "failed", "error": "boom"})):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3") is None


def test_polls_until_completed():
    states = [{"status": "pending"}, {"status": "processing"},
              {"status": "completed", "download_url": "/x"}]
    calls = []

    def fake_get(url, timeout=None, stream=None):
        if "/status/" in url:
            calls.append(url)
            return _resp(states[min(len(calls) - 1, len(states) - 1)])
        return _resp({})

    with patch("notebooklm.requests.post", return_value=_resp({"job_id": "j", "status": "pending"})), \
         patch("notebooklm.requests.get", side_effect=fake_get), \
         patch("notebooklm.time.sleep"), patch("notebooklm.open", create=True):
        out = notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3")
    assert len(calls) == 3
    assert out == "/tmp/x.mp3"


def test_gives_up_after_timeout():
    with patch("notebooklm.requests.post", return_value=_resp({"job_id": "j", "status": "pending"})), \
         patch("notebooklm.requests.get", return_value=_resp({"status": "processing"})), \
         patch("notebooklm.time.sleep"):
        assert notebooklm.generate_audio_review(["http://a"], "/tmp/x.mp3", timeout=30) is None


def test_empty_urls_returns_none():
    assert notebooklm.generate_audio_review([], "/tmp/x.mp3") is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_notebooklm.py -v`
Expected: `ModuleNotFoundError: No module named 'notebooklm'`

- [ ] **Step 3: notebooklm.py 구현**

```python
import time

import requests

from config import (NOTEBOOKLM_API_URL, NOTEBOOKLM_STYLE, NOTEBOOKLM_LANGUAGE,
                    NOTEBOOKLM_TIMEOUT, NOTEBOOKLM_POLL_INTERVAL)

_HTTP_TIMEOUT = 60


def _post(path: str, payload: dict | None = None) -> dict:
    r = requests.post(f"{NOTEBOOKLM_API_URL}{path}", json=payload, timeout=_HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get(path: str) -> dict:
    r = requests.get(f"{NOTEBOOKLM_API_URL}{path}", timeout=_HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def generate_audio_review(urls: list[str], out_path: str, title: str = "",
                          timeout: int = NOTEBOOKLM_TIMEOUT) -> str | None:
    """링크를 NotebookLM 노트북에 올리고 오디오 오버뷰를 만들어 내려받는다.
    NotebookLM 은 부가 기능이므로 어떤 실패도 배치 전체를 멈추지 않는다."""
    urls = [u for u in urls if u]
    if not urls:
        return None
    try:
        # 노트북 하나를 재사용하므로 어제 소스를 먼저 비운다
        _post("/sources/clear")
        up = _post("/sources/upload",
                   {"sources": [{"type": "url", "content": u} for u in urls]})
        if not up.get("overall_success"):
            failed = [r for r in up.get("results", []) if not r.get("success")]
            print(f"[NotebookLM] 소스 업로드 일부 실패: {len(failed)}건")

        prompt = (f"{title} 의 주요 기술 소식들이야. 각 글의 핵심과 서로 어떤 흐름으로 이어지는지 "
                  f"짚어줘.") if title else ""
        job = _post("/audio/generate", {
            "style": NOTEBOOKLM_STYLE,
            "language": NOTEBOOKLM_LANGUAGE,
            **({"prompt": prompt} if prompt else {}),
        })
        job_id = job.get("job_id")
        if not job_id:
            print("[NotebookLM] job_id 를 받지 못했다")
            return None

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st = _get(f"/audio/status/{job_id}")
            status = str(st.get("status", "")).lower()
            if status == "completed":
                break
            if status == "failed":
                print(f"[NotebookLM] 생성 실패: {st.get('error', '')}")
                return None
            time.sleep(NOTEBOOKLM_POLL_INTERVAL)
        else:
            print(f"[NotebookLM] 타임아웃({timeout}s)")
            return None

        r = requests.get(f"{NOTEBOOKLM_API_URL}/audio/download/{job_id}", timeout=_HTTP_TIMEOUT)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        print(f"[NotebookLM] 오디오 저장: {out_path}")
        return out_path
    except Exception as e:
        print(f"[NotebookLM] 실패: {type(e).__name__}: {str(e)[:150]}")
        return None
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_notebooklm.py -v`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add notebooklm.py tests/test_notebooklm.py
git commit -m "feat: NotebookLM 오디오 리뷰 생성 클라이언트"
```

---

### Task 2: 하이라이트에 원문 링크 붙이기

**Files:**
- Modify: `summarizer.py` (`generate_highlights`)
- Modify: `main.py` (`save_html`)
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Produces: `generate_highlights(data) -> list[str]` — 시그니처 유지 (renderer 호환)
- Produces: `generate_highlight_links(data) -> list[dict]` — `[{"text", "url", "source"}]`
  하이라이트 문장과 원문 URL을 함께 준다. NotebookLM 에 넘길 링크의 출처다.

현재 `generate_highlights` 는 LLM 이 만든 문장 5줄만 돌려주어 어느 글에서 나왔는지 알 수 없다.
프롬프트에 번호를 붙여 `번호|요약` 형태로 받아 인덱스로 URL 을 되찾는다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_summarizer.py 에 추가
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_summarizer.py -k highlight_links -v`
Expected: `AttributeError: module 'summarizer' has no attribute 'generate_highlight_links'`

- [ ] **Step 3: summarizer.py 구현**

```python
HIGHLIGHT_LINK_PROMPT = """오늘의 개발/기술 트렌드 항목 목록이야.
가장 중요하고 임팩트 있는 것 5개를 골라줘.

형식: 각 줄에 "번호|한 줄 요약(50자 이내)" 로만 답해. 다른 말 없이.
예: 3|새 모델이 코딩 벤치마크에서 기존 대비 크게 앞섰다

{items_text}"""


def _highlight_candidates(data: dict) -> list[dict]:
    items = []
    for key, tag in (("company_blogs", ""), ("dev_blogs", ""), ("papers", "논문"), ("github", "GitHub")):
        for i in data.get(key, []):
            title = i.get("title_ko") or i.get("title") or i.get("name", "")
            if not title:
                continue
            items.append({"title": title, "url": i.get("url", ""),
                          "source": tag or i.get("source", "")})
    return items[:20]


def generate_highlight_links(data: dict) -> list[dict]:
    """하이라이트 문장과 원문 링크를 함께 돌려준다."""
    cands = _highlight_candidates(data)
    if not cands:
        return []
    items_text = "\n".join(f"{n+1}. [{c['source']}] {c['title']}" for n, c in enumerate(cands))
    response = _run_claude(HIGHLIGHT_LINK_PROMPT.format(items_text=items_text), timeout=90)
    out = []
    for line in (response or "").splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        num, _, text = line.partition("|")
        num = num.strip().lstrip("0") or "0"
        if not num.isdigit():
            continue
        idx = int(num) - 1
        if not 0 <= idx < len(cands) or not text.strip():
            continue
        c = cands[idx]
        out.append({"text": text.strip(), "url": c["url"], "source": c["source"]})
        if len(out) >= 5:
            break
    return out
```

`generate_highlights` 는 그대로 두되, `main.summarize` 에서 링크판을 함께 만들어 재사용한다:
```python
    links = generate_highlight_links(data)
    data["highlight_links"] = links
    data["highlights"] = [l["text"] for l in links] or generate_highlights(data)
```
링크 매핑이 실패하면 기존 방식으로 되돌아간다.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add summarizer.py main.py tests/test_summarizer.py
git commit -m "feat: 하이라이트에 원문 링크 매핑 추가"
```

---

### Task 3: 파이프라인 연결 + 설정

**Files:**
- Modify: `config.py`, `main.py`, `renderer.py`
- Test: `tests/test_main_collect.py`

**Interfaces:**
- Produces: `config.ENABLE_NOTEBOOKLM`(기본 False), `NOTEBOOKLM_API_URL`, `NOTEBOOKLM_STYLE`,
  `NOTEBOOKLM_LANGUAGE`, `NOTEBOOKLM_TIMEOUT`, `NOTEBOOKLM_POLL_INTERVAL`, `AUDIO_DIR`
- 오디오는 `docs/audio/{날짜}.mp3` 로 저장하고, 있으면 일별 페이지에 재생 링크를 넣는다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_main_collect.py 에 추가
def test_audio_step_skipped_when_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", False)
    monkeypatch.setattr(main, "generate_audio_review", lambda *a, **kw: called.append(1))
    main.make_audio({"date": "2026-08-14", "highlight_links": [{"url": "http://a"}]})
    assert called == []


def test_audio_step_passes_highlight_urls(monkeypatch):
    got = {}
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", True)
    monkeypatch.setattr(main, "generate_audio_review",
                        lambda urls, out, title="", **kw: got.update(urls=urls, out=out) or out)
    data = {"date": "2026-08-14",
            "highlight_links": [{"url": "http://a"}, {"url": "http://b"}, {"url": ""}]}
    main.make_audio(data)
    assert got["urls"] == ["http://a", "http://b"]
    assert got["out"].endswith("2026-08-14.mp3")


def test_audio_failure_does_not_break_pipeline(monkeypatch):
    monkeypatch.setattr(main, "ENABLE_NOTEBOOKLM", True)
    monkeypatch.setattr(main, "generate_audio_review",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert main.make_audio({"date": "2026-08-14",
                            "highlight_links": [{"url": "http://a"}]}) is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -k audio -v`
Expected: `AttributeError: module 'main' has no attribute 'make_audio'`

- [ ] **Step 3: config.py 에 설정 추가**

```python
AUDIO_DIR = DOCS_DIR / "audio"

# NotebookLM 오디오 리뷰 (notebooklm-podcast-automator 를 별도로 띄워야 동작한다)
ENABLE_NOTEBOOKLM = os.getenv("ENABLE_NOTEBOOKLM", "0") == "1"
NOTEBOOKLM_API_URL = os.getenv("NOTEBOOKLM_API_URL", "http://127.0.0.1:8000")
NOTEBOOKLM_STYLE = os.getenv("NOTEBOOKLM_STYLE", "deep_dive")
NOTEBOOKLM_LANGUAGE = os.getenv("NOTEBOOKLM_LANGUAGE", "ko")
NOTEBOOKLM_TIMEOUT = int(os.getenv("NOTEBOOKLM_TIMEOUT", "900"))
NOTEBOOKLM_POLL_INTERVAL = int(os.getenv("NOTEBOOKLM_POLL_INTERVAL", "15"))
```

- [ ] **Step 4: main.py 에 단계 추가**

```python
def make_audio(data: dict) -> str | None:
    """하이라이트 링크로 NotebookLM 오디오 리뷰를 만든다. 실패해도 배치는 계속된다."""
    if not ENABLE_NOTEBOOKLM:
        return None
    urls = [l.get("url") for l in data.get("highlight_links", []) if l.get("url")]
    if not urls:
        print("[NotebookLM] 하이라이트 링크가 없어 건너뜀")
        return None
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out = str(AUDIO_DIR / f"{data['date']}.mp3")
    try:
        return generate_audio_review(urls, out, title=f"{data['date']} 기술 트렌드")
    except Exception as e:
        print(f"[NotebookLM] 실패: {type(e).__name__}: {str(e)[:150]}")
        return None
```

`main()` 에서 `save_html` 뒤, `git_commit_push` 앞에 호출한다. 생성된 오디오 파일도 커밋 대상에 넣는다:
```python
    audio_path = make_audio(data)
    ...
    git_commit_push(today_str, audio_path)
```
`git_commit_push` 는 `audio_path` 가 있을 때만 그 파일을 `git add` 한다.

- [ ] **Step 5: 페이지에 재생 링크 노출**

`render_daily_page` 가 `data.get("audio_url")` 이 있으면 하이라이트 섹션 아래에 넣는다:
```python
    if data.get("audio_url"):
        sections += (f'<div class="audio-block"><audio controls preload="none" '
                     f'src="{data["audio_url"]}"></audio>'
                     f'<span>오늘의 오디오 리뷰</span></div>')
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add config.py main.py renderer.py tests/test_main_collect.py
git commit -m "feat: 파이프라인에 NotebookLM 오디오 리뷰 단계 연결"
```

---

### Task 4: 실행 절차 문서화

**Files:**
- Create: `docs/notebooklm-setup.md`

- [ ] **Step 1: 준비 절차를 문서로 남긴다**

사용자가 직접 해야 하는 일(이 저장소가 대신할 수 없는 것):
1. `notebooklm-podcast-automator` 를 클론하고 `uv sync` + `playwright install chromium`
2. NotebookLM 에서 **노트북을 하나 만들고 그 URL** 을 확보
3. `NOTEBOOKLM_URL=<노트북 URL>` 로 서버 기동 → 최초 1회 열리는 Chrome 창에서 **Google 로그인**
4. 이 저장소 `.env` 에 `ENABLE_NOTEBOOKLM=1` 추가 (직접 편집)
5. `python main.py` 실행

- [ ] **Step 2: 커밋**

```bash
git add docs/notebooklm-setup.md
git commit -m "docs: NotebookLM 오디오 리뷰 설정 절차"
```

---

## Self-Review

**커버리지**
- 하이라이트 5건 링크 확보 → Task 2
- NotebookLM 업로드·오디오 생성·다운로드 → Task 1
- 파이프라인 연결 → Task 3
- 실행 준비 절차 → Task 4

**알려진 제약 (사용자 확인 필요)**
- 이 도구는 **노트북을 만들지 않는다.** 기존 노트북 URL 을 `NOTEBOOKLM_URL` 로 줘야 하고,
  매일 같은 노트북을 비우고 재사용한다.
- **최초 1회 Google 로그인이 사람 손으로 필요하다.** 세션이 만료되면 다시 로그인해야 하며,
  그때까지 오디오 생성은 실패한다(배치의 나머지는 정상 동작).
- launchd 무인 실행 환경에서는 Chrome 창을 띄울 수 있는지가 관건이다. 이 저장소에는
  `2026-08-03-fix-launchd-claude-auth.md` 로 남은 유사 사고 이력이 있다.
- 오디오 파일을 저장소에 커밋하면 용량이 누적된다. mp3 한 편이 수 MB 이므로
  일정 기간 뒤 정리하거나 `.gitignore` 로 뺄지 결정이 필요하다.
