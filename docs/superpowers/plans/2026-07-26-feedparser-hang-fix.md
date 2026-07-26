# feedparser 무한 대기 수정 + 1시간 워치독 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `feedparser.parse(url)`가 timeout 없이 소켓을 열어 무한 대기하는 근본 원인을 제거하고, 향후 어떤 원인으로든 배치가 멈추더라도 1시간 내에 강제 종료되도록 방어선을 추가한다.

**Architecture:** RSS/arXiv/Reddit 세 소스 모두 `requests.get(url, timeout=15)`로 먼저 콘텐츠를 받아온 뒤 `feedparser.parse(response.content)`로 파싱하도록 변경한다 (다른 소스 파일들이 이미 쓰는 패턴과 동일). `main.py`에는 `signal.alarm(3600)` 기반 워치독을 추가해 프로세스 전체에 상한선을 건다.

**Tech Stack:** Python 3.10, requests, feedparser, pytest, unittest.mock

## Global Constraints

- 기존 코드 스타일 유지, 불필요한 리팩토링 금지
- 새 의존성 추가 금지 (requests는 이미 사용 중)
- `sources/scraper.py`, `sources/github.py`, `sources/hackernews.py`, `notifier.py`는 이미 `timeout=`을 쓰고 있으므로 변경 대상 아님

---

### Task 1: sources/rss.py — requests로 fetch 후 feedparser.parse

**Files:**
- Modify: `sources/rss.py:22` (`fetch_rss_entries` 함수)
- Test: `tests/test_rss.py`

**Interfaces:**
- Consumes: `requests.get`, `feedparser.parse`
- Produces: `fetch_rss_entries(name, url, max_items=MAX_BLOG_ITEMS, **kwargs) -> list[dict]` — 시그니처 변경 없음

- [ ] **Step 1: 테스트를 requests.get 모킹에 맞게 수정**

```python
from unittest.mock import patch, MagicMock
from sources.rss import fetch_rss_entries

def _mock_feed():
    entry = MagicMock()
    entry.title = "New Post"
    entry.link = "https://example.com/post"
    entry.get = lambda k, d="": "This is a summary." if k == "summary" else d
    entry.published_parsed = (2026, 5, 31, 12, 0, 0, 5, 151, 0)
    feed = MagicMock()
    feed.entries = [entry]
    return feed

def test_fetch_rss_entries_returns_list():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp), \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert isinstance(items, list)

def test_fetch_rss_entries_parses_entry():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp), \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert len(items) == 1
    assert items[0]["title"] == "New Post"
    assert items[0]["url"] == "https://example.com/post"
    assert items[0]["source"] == "Test Blog"
    assert "summary" in items[0]

def test_fetch_rss_entries_uses_timeout():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.rss.requests.get", return_value=mock_resp) as mock_get, \
         patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert mock_get.call_args.kwargs.get("timeout") == 15
```

- [ ] **Step 2: 테스트 실행해서 실패 확인 (아직 requests.get 안 씀)**

Run: `.venv/bin/pytest tests/test_rss.py -v`
Expected: `test_fetch_rss_entries_uses_timeout`가 `sources.rss.requests`가 없다는 AttributeError로 FAIL

- [ ] **Step 3: sources/rss.py 수정**

```python
import feedparser
import requests
from datetime import datetime, timezone, timedelta, time
from config import RSS_SOURCES, MAX_BLOG_ITEMS

KST = timezone(timedelta(hours=9))
_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}

def _get_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def _today_cutoff() -> datetime:
    now_kst = datetime.now(KST)
    return now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS, **kwargs) -> list[dict]:
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    cutoff = _today_cutoff()
    for entry in feed.entries:
        pub = _get_date(entry)
        if pub is None or pub < cutoff:
            continue
        summary = getattr(entry, "summary", "") or ""
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "source": name,
            "summary": summary[:500],
            "category": kwargs.get("category", "dev"),
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_blogs() -> list[dict]:
    all_items = []
    for source in RSS_SOURCES:
        try:
            all_items.extend(fetch_rss_entries(
                source["name"], source["url"], category=source.get("category", "dev")
            ))
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
    return all_items
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/pytest tests/test_rss.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add sources/rss.py tests/test_rss.py
git commit -m "fix: rss fetch에 requests timeout 적용해 무한 대기 방지"
```

---

### Task 2: sources/arxiv.py — 동일 패턴 적용

**Files:**
- Modify: `sources/arxiv.py:4` (`fetch_arxiv_papers` 함수)
- Test: `tests/test_arxiv.py`

**Interfaces:**
- Consumes: `requests.get`, `feedparser.parse`
- Produces: `fetch_arxiv_papers(feed_url) -> list[dict]` — 시그니처 변경 없음

- [ ] **Step 1: 테스트를 requests.get 모킹에 맞게 수정**

```python
from unittest.mock import patch, MagicMock
from sources.arxiv import fetch_arxiv_papers

def _mock_feed():
    entry = MagicMock()
    entry.title = "Attention Is All You Need 2.0"
    entry.link = "https://arxiv.org/abs/2601.00001"
    entry.get = lambda k, d="": "Abstract of the paper about transformers." if k == "summary" else d
    feed = MagicMock()
    feed.entries = [entry]
    return feed

def test_fetch_arxiv_papers_returns_list():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.arxiv.requests.get", return_value=mock_resp), \
         patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert isinstance(items, list)

def test_fetch_arxiv_papers_parses_entry():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.arxiv.requests.get", return_value=mock_resp), \
         patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert items[0]["title"] == "Attention Is All You Need 2.0"
    assert "arxiv.org" in items[0]["url"]
    assert "abstract" in items[0]

def test_fetch_arxiv_papers_uses_timeout():
    mock_resp = MagicMock(content=b"<rss></rss>")
    with patch("sources.arxiv.requests.get", return_value=mock_resp) as mock_get, \
         patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert mock_get.call_args.kwargs.get("timeout") == 15
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/pytest tests/test_arxiv.py -v`
Expected: FAIL (`sources.arxiv.requests` 없음)

- [ ] **Step 3: sources/arxiv.py 수정**

```python
import feedparser
import requests
from config import ARXIV_FEEDS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}

def fetch_arxiv_papers(feed_url: str) -> list[dict]:
    resp = requests.get(feed_url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        items.append({
            "title": getattr(entry, "title", "").replace("\n", " ").strip(),
            "url": getattr(entry, "link", ""),
            "abstract": getattr(entry, "summary", "")[:600],
        })
    return items

def fetch_all_papers() -> list[dict]:
    seen, all_items = set(), []
    for url in ARXIV_FEEDS:
        try:
            for p in fetch_arxiv_papers(url):
                if p["url"] not in seen:
                    seen.add(p["url"])
                    all_items.append(p)
        except Exception as e:
            print(f"[arXiv] {url} 실패: {e}")
    return all_items
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/pytest tests/test_arxiv.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add sources/arxiv.py tests/test_arxiv.py
git commit -m "fix: arxiv fetch에 requests timeout 적용해 무한 대기 방지"
```

---

### Task 3: sources/reddit.py — 동일 패턴 적용 (기존 테스트 없음)

**Files:**
- Modify: `sources/reddit.py:12` (`fetch_subreddit` 함수)

**Interfaces:**
- Consumes: `requests.get`, `feedparser.parse`
- Produces: `fetch_subreddit(name, max_items=MAX_REDDIT_ITEMS) -> list[dict]` — 시그니처 변경 없음

- [ ] **Step 1: sources/reddit.py 수정**

```python
import feedparser
import requests
from datetime import datetime, timezone, timedelta, time
from config import REDDIT_SUBREDDITS, MAX_REDDIT_ITEMS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}
KST = timezone(timedelta(hours=9))

def _today_cutoff() -> datetime:
    now_kst = datetime.now(KST)
    return now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_subreddit(name: str, max_items: int = MAX_REDDIT_ITEMS) -> list[dict]:
    url = f"https://www.reddit.com/r/{name}/top.rss?t=day"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    cutoff = _today_cutoff()
    items = []
    for entry in feed.entries:
        pub = getattr(entry, "published_parsed", None)
        if pub:
            try:
                if datetime(*pub[:6], tzinfo=timezone.utc) < cutoff:
                    continue
            except Exception:
                pass
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        items.append({
            "title": title,
            "url": link,
            "source": f"r/{name}",
            "summary": "",
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_reddit() -> list[dict]:
    all_items = []
    for name in REDDIT_SUBREDDITS:
        try:
            all_items.extend(fetch_subreddit(name))
        except Exception as e:
            print(f"[Reddit] r/{name} 실패: {e}")
    return all_items
```

참고: 원본에서 `url = getattr(entry, "link", "")`가 바깥쪽 `url` 파라미터(피드 URL)를 매 루프마다 덮어쓰고 있었음(버그였지만 각 entry의 `url` 필드 값 자체는 정상 계산됨, 루프 밖에서 `url` 변수를 재사용하지 않으므로 부작용 없음) — 변수명 충돌을 피하려 `link`로 개명. 동작 변화 없음.

- [ ] **Step 2: 기존 테스트 스위트 실행 (reddit 전용 테스트 없음, 회귀만 확인)**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS (전체)

- [ ] **Step 3: 커밋**

```bash
git add sources/reddit.py
git commit -m "fix: reddit fetch에 requests timeout 적용해 무한 대기 방지"
```

---

### Task 4: main.py — 1시간 하드 워치독

**Files:**
- Modify: `main.py:1-16` (import), `main.py:180` (`main()` 함수 시작부)

**Interfaces:**
- Consumes: 표준 라이브러리 `signal`
- Produces: 없음 (프로세스 레벨 안전장치)

- [ ] **Step 1: main.py에 signal import 및 워치독 추가**

`main.py` 상단 import에 `signal` 추가:

```python
import json
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime
```

`main()` 함수 시작부 수정 (main.py:180-183):

```python
def _timeout_handler(signum, frame):
    print("[TIMEOUT] 1시간 초과, 강제 종료")
    raise SystemExit(1)


def main():
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(3600)

    today = date.today()
    today_str = str(today)
    data = collect(today_str)
```

- [ ] **Step 2: 워치독이 실제로 발동하는지 수동 확인**

Run:
```bash
.venv/bin/python -c "
import signal, time
def h(s, f):
    print('[TIMEOUT] fired')
    raise SystemExit(1)
signal.signal(signal.SIGALRM, h)
signal.alarm(2)
time.sleep(5)
print('should not reach here')
"
```
Expected: 2초 뒤 `[TIMEOUT] fired` 출력 후 프로세스 종료, `should not reach here` 출력 안 됨 (exit code 1)

- [ ] **Step 3: 전체 테스트 스위트 회귀 확인**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS (전체, 워치독 관련 신규 유닛 테스트는 없음 — signal.alarm은 프로세스 전역 상태라 pytest 안에서 안전하게 단위 테스트하기 어려움. Step 2의 수동 확인으로 대체)

- [ ] **Step 4: 커밋**

```bash
git add main.py
git commit -m "feat: 배치 전체에 1시간 하드 타임아웃 워치독 추가"
```

---

### Task 5: 좀비 프로세스 정리 + 배치 재실행 (운영, 코드 변경 없음)

**Files:** 없음 (운영 작업)

- [ ] **Step 1: 현재 7일 넘게 멈춰있는 PID 종료**

Run: `kill 52054` (확인: `ps -p 52054`로 종료 확인, 안 죽으면 `kill -9 52054`)

- [ ] **Step 2: launchd 잡이 재시작 가능한 상태인지 확인**

Run: `launchctl print gui/$(id -u)/com.karellen.trending-tech | grep state`
Expected: `state = not running` (아까는 `state = running`이었음)

- [ ] **Step 3: 배치 수동 실행 (오늘자 백필)**

Run: `cd /Users/kimeunmi/source/project/trending-tech && .venv/bin/python main.py`
Expected: `[완료] 2026-07-26` 출력, `docs/2026-07-26.html`/`.json` 생성, git 커밋+푸시 성공, Slack 알림 전송 (SLACK_WEBHOOK_URL 설정 시)

- [ ] **Step 4: 결과 확인**

Run: `git log --oneline -1` (커밋 확인), `git status` (clean 확인)
