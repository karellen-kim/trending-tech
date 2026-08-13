# 소스 확장 + 날짜필터 교정 + 핵심요약/SVG/아코디언 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기술 블로그 소스를 19개에서 60개 이상으로 확장하고, HN/Reddit 수집을 중단하며, **오늘 글인지 판정과 요약·제목번역을 LLM 호출 1회로 통합**하고, 각 글을 "핵심 내용 요약 + 개념 SVG"로 보여주되 제목만 노출하고 클릭 시 펼쳐지는 아코디언 UI로 바꾼다.

**Architecture:** 모든 소스에서 **최신 3건만** 가져온다. 수집 단계는 날짜로 거르지 않고 발행일 힌트만 실어 보낸다. 분석 단계에서 `claude -p` **단일 호출**이 `{is_today, pub_date, title_ko, summary}` JSON을 돌려주고, `is_today=false`인 항목은 리스트에서 제외한다. 요약이 짧으면 원문 본문을 먼저 보강한다. 상위 N건에 개념 SVG를 생성하며, SVG는 XML 파싱으로 검증하고 스크립트/이벤트 핸들러/외부참조/DOCTYPE을 제거한 뒤에만 삽입한다. 렌더러는 `<details>/<summary>` 아코디언으로 전환한다.

**모델:** `claude-haiku-4-5-20251001` (sonnet 아님 — `summarizer.py:27`에서 확인)

**Tech Stack:** Python 3.10+, requests, feedparser, BeautifulSoup4, `claude` CLI (haiku-4-5), 순수 HTML/CSS

**Spec:** 이 문서 (사용자 요청 + 실측 데이터)

## Global Constraints

- Python 3.10+ / 새 서드파티 의존성 추가 금지 (`requirements.txt` 범위 내에서만)
- `.env` 수정 금지, `git push` 금지 (사용자 명시 요청 시에만)
- 기존 코드 스타일 유지: 한국어 주석, 시그니처 수준 타입 힌트, 불필요한 docstring 추가 금지
- 모든 소스 URL은 실측 검증된 것만 사용 (`scratchpad/feed-probe*.json`)
- 요약/번역/SVG는 전부 `summarizer._run_claude` 경유 (모델 `claude-haiku-4-5-20251001`)
- **소스당 검사 대상은 최신 3건** — 이 값이 `MAX_BLOG_ITEMS`, `MAX_SCRAPER_ITEMS` 양쪽에 적용된다

---

## 근거 데이터 (전부 이 세션에서 실측)

**1. RSS 피드 검증** — 후보 82개 중 55개 통과(200 + 엔트리 존재 + 날짜 파싱 가능), 2차 재시도로 NAVER D2 등 3개, 3차 rate-limit 회피로 Medium 계열 8개 추가. **총 63개 검증 완료.**

**2. 기존 config의 깨진 소스**
- `https://www.deeplearning.ai/the-batch/feed/` (config.py:37) → **404**. 대체 경로 3개 모두 404/500. 삭제 대상.
- `https://fchollet.substack.com/feed` (config.py:25) → 최신 글 2023-10-09.

**3. RSS 미제공 확인 (추가 불가)** — Anthropic, LinkedIn, Shopify, DoorDash(403), 우아한형제들(403), RIDI(403), OpenSource Connections(403), NAVER CLOVA(entries=0), mlops.systems, Made With ML, Full Stack Deep Learning, MLOps Community, deepset, Alex Petrov(ConnectionError), Geoffrey Hinton, ABLY(404), Uber(RSS 없음 → 스크래퍼 유지), 당근·Coupang(Medium 429로 미검증, URL 패턴은 유효)

**4. 요약 길이 분포** (52개 피드 497개 엔트리)
- `entry.summary` 텍스트 150자 이상: **272개 (55%)**. 나머지 45%는 `summarizer.py:47`의 `len < 150` 가드에 걸려 **요약이 빈 문자열**이 된다.
- 전 엔트리 요약 불가 피드 16개: Google Research, Databricks, Kakao Tech, LY Corp, 컬리, 쏘카, 뱅크샐러드, Gregor Hohpe, Karpathy, Sebastian Raschka, fast.ai, Denny Britz, Nathan Lambert, Eugene Yan, Doug Turnbull, Shreya Shankar
- **결론: 본문 fetch(Task 5) 없이는 국내 블로그 대부분이 요약도 SVG도 못 만든다.**

**5. Alibaba 요약 실패 원인**
```
status=200 html_len=51470 extracted_len=36
head: 'Blog Events Webinars Tutorials Forum'
```
글 본문이 JS 렌더링이라 `_fetch_article_text`가 네비게이션만 긁는다. **Alibaba는 RSS도 없다** — `/blog/rss`, `/blog/feed`, `/rss.xml`, `/blog.rss` 모두 status=200이지만 entries=0(HTML 반환).

**6. 날짜 필터가 새는 지점** (8/13 페이지 기준)
- Alibaba 목록 페이지 재현: **날짜 찾음 14 / 못 찾음 20**. `scraper.py:139`가 `if date_found and not is_today: continue`라서 **날짜를 못 읽으면 그대로 포함**된다. 8/13에 실린 5건이 이 경로다. `Wan3.0` 글은 지금 파싱하면 **May 21, 2026**.
- Spotify는 URL의 `/YYYY/M/`만 보고 "이번 달 또는 지난달"을 통과시킨다(scraper.py:169-171). 8/13 페이지의 2건은 `/2026/7/` — **7월 글**.
- RSS 경로는 `pub < cutoff`만 검사(rss.py:31) → **미래 날짜 상한 없음**.
- Simon Willison 3건은 **오작동이 아니다**: UTC 15:08~23:59 → KST 8/13 00:08~08:59. slug만 UTC 기준 Aug/12.

---

### Task 1: RSS 수집 — 최신 3건 + 발행일 힌트 전달 (날짜 판정은 LLM에 위임)

**Files:**
- Modify: `sources/rss.py:19-43`
- Test: `tests/test_rss.py`

**Interfaces:**
- Produces: `fetch_rss_entries(name, url, max_items=MAX_BLOG_ITEMS, **kwargs)` — 시그니처 불변.
  동작 변경: 피드 엔트리 **앞에서 3건만** 반환하고, **날짜로 거르지 않는다.**
  각 항목에 `"pub_hint"` 키를 추가한다 — 피드가 준 발행일 원문(`entry.published`/`updated`)과
  파싱된 ISO 문자열을 합친 문자열. 분석 단계(Task 6)에서 LLM이 이 값을 근거로 오늘 글인지 판정한다.
- `_today_cutoff()`는 더 이상 쓰지 않으므로 삭제한다. `_get_date()`는 `pub_hint` 생성에 계속 쓴다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_rss.py 에 추가
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

KST = timezone(timedelta(hours=9))

def _feed_xml(dates):
    items = "".join(
        f"<item><title>t{i}</title><link>http://x/{i}</link>"
        f"<description>본문{i}</description><pubDate>{d}</pubDate></item>"
        for i, d in enumerate(dates)
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>".encode()

def _mock_resp(dates):
    resp = Mock(status_code=200, content=_feed_xml(dates))
    resp.raise_for_status = Mock()
    return resp

def test_returns_only_top_3_entries():
    """최신 3건만 가져온다 — 4번째부터는 보지 않는다"""
    from sources import rss
    d = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([d] * 10)):
        items = rss.fetch_rss_entries("s", "http://f", max_items=3)
    assert len(items) == 3

def test_does_not_filter_by_date():
    """날짜 판정은 LLM(Task 6)이 한다 — 수집 단계는 거르지 않는다"""
    from sources import rss
    old = (datetime.now(KST) - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0900")
    with patch("sources.rss.requests.get", return_value=_mock_resp([old])):
        items = rss.fetch_rss_entries("s", "http://f")
    assert len(items) == 1

def test_pub_hint_carries_parsed_date():
    from sources import rss
    d = "Thu, 13 Aug 2026 01:00:00 +0900"
    with patch("sources.rss.requests.get", return_value=_mock_resp([d])):
        items = rss.fetch_rss_entries("s", "http://f")
    hint = items[0]["pub_hint"]
    assert "2026-08-13" in hint, hint          # KST 로 환산된 ISO 날짜
    assert "13 Aug 2026" in hint, hint         # 피드 원문도 함께 남긴다

def test_pub_hint_is_unknown_when_feed_has_no_date():
    from sources import rss
    xml = (b"<?xml version='1.0'?><rss version='2.0'><channel>"
           b"<item><title>t</title><link>http://x</link><description>d</description></item>"
           b"</channel></rss>")
    resp = Mock(status_code=200, content=xml)
    resp.raise_for_status = Mock()
    with patch("sources.rss.requests.get", return_value=resp):
        items = rss.fetch_rss_entries("s", "http://f")
    assert items[0]["pub_hint"] == "unknown"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_rss.py -k "top_3 or filter_by_date or pub_hint" -v`
Expected: `test_does_not_filter_by_date` FAIL(현재 rss.py:31이 거른다), `pub_hint` 테스트 2건 KeyError

- [ ] **Step 3: rss.py 수정**

```python
def _pub_hint(entry) -> str:
    """LLM 이 오늘 글인지 판정할 근거. 피드 원문 날짜와 KST 환산 날짜를 함께 준다."""
    raw = (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()
    pub = _get_date(entry)
    if pub is None:
        return raw or "unknown"
    kst = pub.astimezone(KST)
    return f"{kst.strftime('%Y-%m-%d %H:%M')} KST (피드 원문: {raw})" if raw else \
           f"{kst.strftime('%Y-%m-%d %H:%M')} KST"

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS, **kwargs) -> list[dict]:
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    # 피드는 최신순이므로 앞에서 max_items 건만 가져온다.
    # 오늘 글인지 판정은 summarizer.analyze_item 이 LLM 호출 한 번으로 처리한다.
    for entry in feed.entries[:max_items]:
        summary = getattr(entry, "summary", "") or ""
        items.append({
            "title": getattr(entry, "title", ""),
            "url": getattr(entry, "link", ""),
            "source": name,
            "summary": summary[:500],
            "pub_hint": _pub_hint(entry),
            "category": kwargs.get("category", "dev"),
        })
    return items
```
`_today_cutoff()`를 삭제한다.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_rss.py -v`
Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add sources/rss.py tests/test_rss.py
git commit -m "refactor: RSS 최신 3건만 수집, 발행일 힌트 전달 (날짜 판정은 LLM으로 이관)"
```

---

### Task 2: 스크래퍼 정리 — 상위 3건 + 발행일 힌트, Spotify 제거

**Files:**
- Modify: `sources/scraper.py:79-151` (fetch_uber, fetch_alibaba), `sources/scraper.py:153-195` (fetch_spotify 삭제)
- Test: `tests/test_scraper.py` (신규)

**Interfaces:**
- Produces: `_fetch_article_date(url) -> str` — 글 페이지에서 발견한 첫 날짜 문자열, 없으면 `""`
- Produces: `fetch_alibaba(max_items=MAX_SCRAPER_ITEMS)`, `fetch_uber(max_items=MAX_SCRAPER_ITEMS)` —
  목록 상위 `max_items`건만 다루고, **날짜로 거르지 않는다.** 각 항목에 `"pub_hint"`를 넣는다
  (글 페이지에서 찾은 날짜 문자열, 못 찾으면 `"unknown"`). 판정은 Task 6의 LLM이 한다.
- `fetch_spotify`와 `_SCRAPERS["Spotify Engineering"]` 삭제 — RSS(`engineering.atspotify.com/feed`)로 전환
- `_is_today()`는 더 이상 호출되지 않지만, 되돌리기 쉽게 함수는 남겨둔다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_scraper.py
from unittest.mock import patch
from sources import scraper

def test_alibaba_only_opens_top_n_articles():
    """목록 전체를 열면 요청이 34배가 된다(실측 34건) — 상위 max_items 건만 연다"""
    links = "".join(
        f'<a href="https://www.alibabacloud.com/blog/article-number-{i}-long-title_{i}">'
        f'Article Number {i} With A Long Title</a>' for i in range(10)
    )
    opened = []
    with patch("sources.scraper.requests.get") as g:
        g.return_value.text = f"<html><body>{links}</body></html>"
        g.return_value.status_code = 200
        g.return_value.raise_for_status = lambda: None
        with patch("sources.scraper._fetch_article_date",
                   side_effect=lambda u: opened.append(u) or "August 14, 2026"), \
             patch("sources.scraper._fetch_article_text", return_value="본문" * 200):
            items = scraper.fetch_alibaba(max_items=3)
    assert len(opened) == 3
    assert len(items) == 3

def test_alibaba_sets_pub_hint_unknown_when_no_date():
    html = ('<html><body>'
            '<a href="https://www.alibabacloud.com/blog/some-long-article-title_1">'
            'Some Long Article Title Here</a></body></html>')
    with patch("sources.scraper.requests.get") as g:
        g.return_value.text = html
        g.return_value.status_code = 200
        g.return_value.raise_for_status = lambda: None
        with patch("sources.scraper._fetch_article_date", return_value=""), \
             patch("sources.scraper._fetch_article_text", return_value="본문" * 200):
            items = scraper.fetch_alibaba()
    assert len(items) == 1
    assert items[0]["pub_hint"] == "unknown"

def test_spotify_scraper_is_removed():
    assert not hasattr(scraper, "fetch_spotify")
    assert "Spotify Engineering" not in scraper._SCRAPERS
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_scraper.py -v`
Expected: 3건 모두 FAIL (`_fetch_article_date` 없음, `pub_hint` 없음, Spotify 존재)

- [ ] **Step 3: scraper.py 수정**

`_fetch_uber_article`의 날짜 추출을 공용 함수로 뽑는다:
```python
def _fetch_article_date(url: str) -> str:
    """글 페이지에서 가장 먼저 나오는 날짜 문자열. 못 찾으면 빈 문자열."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        m = _UBER_DATE_PATTERN.search(resp.text)
        return m.group() if m else ""
    except Exception:
        return ""
```

`fetch_alibaba`를 교체한다:
```python
def fetch_alibaba(max_items: int = MAX_SCRAPER_ITEMS) -> list[dict]:
    resp = requests.get("https://www.alibabacloud.com/blog", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, candidates = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("https://www.alibabacloud.com/blog/"):
            continue
        if href.rstrip("/") == "https://www.alibabacloud.com/blog" or href in seen:
            continue
        title = a.get_text(strip=True)
        if len(title) < 15:
            continue
        seen.add(href)
        candidates.append((title, href))
        if len(candidates) >= max_items:
            break

    # 목록 페이지에는 날짜 없는 카드가 많아(실측 20/34) 개별 글에서 발행일 문자열을 가져온다.
    # 오늘 글인지 판정은 summarizer.analyze_item 이 한다.
    items = []
    for title, href in candidates:
        items.append({
            "title": title,
            "url": href,
            "source": "Alibaba Cloud Blog",
            "summary": "",
            "content": _fetch_article_text(href),
            "pub_hint": _fetch_article_date(href) or "unknown",
        })
    return items
```

`fetch_uber`도 같은 방식으로 바꾼다 — 날짜로 `continue` 하지 않고 `pub_hint`에 담는다.
`_fetch_uber_article`이 (날짜, 본문)을 한 번의 요청으로 주므로 그 값을 그대로 쓴다:
```python
        pub_date, content = _fetch_uber_article(href)
        items.append({
            "title": title,
            "url": href,
            "source": "Uber Engineering",
            "summary": "",
            "content": content,
            "pub_hint": pub_date or "unknown",
        })
        if len(items) >= max_items:
            break
```

`fetch_spotify` 함수 전체와 `_SCRAPERS`의 Spotify 항목을 삭제한다.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_scraper.py -v`
Expected: 3 passed

- [ ] **Step 5: 실제 호출로 확인**

Run: `.venv/bin/python -c "from sources.scraper import fetch_alibaba, fetch_uber; [print(i['source'], i['pub_hint'], i['title'][:40]) for i in fetch_alibaba() + fetch_uber()]"`
Expected: 최대 6건, 각각 pub_hint 출력. 출력을 보고에 남긴다.

- [ ] **Step 6: 커밋**

```bash
git add sources/scraper.py tests/test_scraper.py
git commit -m "refactor: 스크래퍼 상위 3건 + 발행일 힌트 전달, Spotify 제거(RSS 전환)"
```

---

### Task 3: RSS 소스 확장 + 상한/플래그 추가

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py` (신규)

**Interfaces:**
- Produces: `RSS_SOURCES` 각 항목 `{"name","url","category"}`, category는 `"company"|"dev"`
- Produces: `MAX_BLOG_ITEMS = 3`, `MAX_SCRAPER_ITEMS = 3`, `MAX_COMPANY_TOTAL`, `MAX_DEV_TOTAL`,
  `MAX_BODY_FETCH`, `ENABLE_SVG`, `MAX_SVG_ITEMS`, `SUMMARY_WORKERS`, `RSS_WORKERS`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_config.py
import config

def test_rss_sources_have_required_keys():
    for s in config.RSS_SOURCES:
        assert set(s.keys()) == {"name", "url", "category"}, s
        assert s["category"] in ("company", "dev"), s
        assert s["url"].startswith("http"), s

def test_no_duplicate_names_or_urls():
    names = [s["name"] for s in config.RSS_SOURCES]
    urls = [s["url"] for s in config.RSS_SOURCES]
    assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
    assert len(urls) == len(set(urls)), [u for u in urls if urls.count(u) > 1]

def test_scraper_and_rss_do_not_overlap():
    """같은 소스가 양쪽에 있으면 main.py:58-59 에서 중복 수집된다"""
    rss_names = {s["name"] for s in config.RSS_SOURCES}
    scraper_names = {s["name"] for s in config.SCRAPER_SOURCES}
    assert not (rss_names & scraper_names), rss_names & scraper_names

def test_every_scraper_source_has_an_implementation():
    from sources.scraper import _SCRAPERS
    for s in config.SCRAPER_SOURCES:
        assert s["name"] in _SCRAPERS, f"{s['name']} 은 파서가 없어 조용히 스킵된다"

def test_broken_feed_removed():
    urls = {s["url"] for s in config.RSS_SOURCES}
    assert "https://www.deeplearning.ai/the-batch/feed/" not in urls  # HTTP 404 실측

def test_top_n_limit_is_three():
    assert config.MAX_BLOG_ITEMS == 3
    assert config.MAX_SCRAPER_ITEMS == 3

def test_source_count_expanded():
    assert len(config.RSS_SOURCES) >= 55
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: `test_every_scraper_source_has_an_implementation` FAIL(Discord Blog·Anthropic News는 파서 없음),
`test_top_n_limit_is_three` FAIL, `test_source_count_expanded` FAIL

- [ ] **Step 3: config.py 갱신**

검증 완료된 63개 피드를 `RSS_SOURCES`에 넣는다. 출처는 `scratchpad/feed-probe.json`(55) +
`feed-probe2.json`(NAVER D2, Martin Fowler) + `feed-probe3.json`(Medium 계열 8).
그룹은 주석으로만 표시하고 `category`는 company/dev 두 값만 쓴다.

`SCRAPER_SOURCES`는 RSS가 없고 파서가 있는 것만:
```python
SCRAPER_SOURCES = [
    {"name": "Uber Engineering", "url": "https://www.uber.com/en-US/blog/engineering/"},
    {"name": "Alibaba Cloud Blog", "url": "https://www.alibabacloud.com/blog"},
]
```

상한/플래그:
```python
MAX_GITHUB_ITEMS = 5
MAX_PAPER_ITEMS = 5
MAX_BLOG_ITEMS = 3        # 소스당 검사할 최신 글 수
MAX_SCRAPER_ITEMS = 3
MAX_COMPANY_TOTAL = 25    # 기술블로그 섹션 하루 전체 상한
MAX_DEV_TOTAL = 20        # 개발자블로그 섹션 하루 전체 상한
MAX_BODY_FETCH = 40       # 요약이 짧아 본문을 새로 받을 최대 건수
ENABLE_SVG = True
MAX_SVG_ITEMS = 8
SUMMARY_WORKERS = 4
RSS_WORKERS = 8
```
`MAX_HN_ITEMS`, `MAX_REDDIT_ITEMS`, `REDDIT_SUBREDDITS`는 되돌리기 쉽게 남겨둔다.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add config.py tests/test_config.py
git commit -m "feat: 검증된 RSS 소스 63개로 확장, 소스당 최신 3건 상한"
```

---

### Task 4: HN/Reddit 수집 중단 (코드는 유지) + RSS 병렬화

**Files:**
- Modify: `main.py:9,12,41-75,78-87,97-99`, `summarizer.py:57-75`, `sources/rss.py:45-54`
- Test: `tests/test_main_collect.py` (신규), `tests/test_rss.py`

**Interfaces:**
- Produces: `collect()` 반환 dict에서 `"hn"`, `"reddit"` 키 제거. `renderer`는 `data.get("hn", [])`를 쓰므로 그대로 동작한다.
- `sources/hackernews.py`, `sources/reddit.py`, renderer의 hn-reddit 섹션은 **삭제하지 않는다**
- Produces: `fetch_all_blogs()` 시그니처 불변, 내부 병렬. 순서 미보장.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_main_collect.py
from unittest.mock import patch
import main

def test_collect_excludes_hn_and_reddit():
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-08-14")
    assert "hn" not in data and "reddit" not in data
```

```python
# tests/test_rss.py 에 추가
def test_fetch_all_blogs_runs_in_parallel(monkeypatch):
    import time
    from sources import rss
    monkeypatch.setattr(rss, "RSS_SOURCES",
                        [{"name": f"s{i}", "url": f"http://x/{i}", "category": "dev"} for i in range(8)])
    monkeypatch.setattr(rss, "enrich_with_body", lambda items, **kw: items)

    def slow(name, url, **kw):
        time.sleep(0.3)
        return [{"title": name, "url": url, "source": name, "summary": "", "category": "dev"}]

    monkeypatch.setattr(rss, "fetch_rss_entries", slow)
    t0 = time.monotonic()
    items = rss.fetch_all_blogs()
    assert len(items) == 8
    assert time.monotonic() - t0 < 1.2

def test_fetch_all_blogs_survives_one_failure(monkeypatch):
    from sources import rss
    monkeypatch.setattr(rss, "RSS_SOURCES", [
        {"name": "ok", "url": "http://ok", "category": "dev"},
        {"name": "bad", "url": "http://bad", "category": "dev"},
    ])
    monkeypatch.setattr(rss, "enrich_with_body", lambda items, **kw: items)

    def maybe_fail(name, url, **kw):
        if name == "bad":
            raise RuntimeError("boom")
        return [{"title": "t", "url": url, "source": name, "summary": "", "category": "dev"}]

    monkeypatch.setattr(rss, "fetch_rss_entries", maybe_fail)
    assert len(rss.fetch_all_blogs()) == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py tests/test_rss.py -v`
Expected: `test_collect_excludes_hn_and_reddit` FAIL, `test_fetch_all_blogs_runs_in_parallel` FAIL(약 2.4s)

- [ ] **Step 3: main.py 수정**

- import 2줄(main.py:9,12) 삭제
- `collect()`에서 `f_hn`/`f_rd` submit·result 삭제, `max_workers=6` → `4`
- 반환 dict에서 `"hn"`, `"reddit"` 삭제, 로그에서 HN/Reddit 카운트 제거
- `summarize()`의 `data["hn"]`·`data["reddit"]` 줄 삭제
- `save_html()` 하이라이트 폴백(main.py:97-99)의 `data["hn"]` 참조 →
  `[i.get("title","") for i in data["company_blogs"][:2]]`

- [ ] **Step 4: summarizer.generate_highlights에서 HN/Reddit 루프 삭제**

`summarizer.py:65-68` 두 for 루프 제거.

- [ ] **Step 5: rss.fetch_all_blogs 병렬화**

```python
from concurrent.futures import ThreadPoolExecutor
from config import RSS_WORKERS

def fetch_all_blogs() -> list[dict]:
    def one(source):
        try:
            return fetch_rss_entries(
                source["name"], source["url"], category=source.get("category", "dev")
            )
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
            return []

    all_items = []
    with ThreadPoolExecutor(max_workers=RSS_WORKERS) as ex:
        for items in ex.map(one, RSS_SOURCES):
            all_items.extend(items)
    return enrich_with_body(all_items)
```
(`enrich_with_body`는 Task 5에서 만든다. 이 Task에서는 임시로 `return all_items`로 두고 Task 5에서 연결한다.)

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과. `tests/test_renderer.py`는 자체 fixture 기반이라 계속 통과해야 한다.

- [ ] **Step 7: 커밋**

```bash
git add main.py summarizer.py sources/rss.py tests/test_main_collect.py tests/test_rss.py
git commit -m "feat: HN/Reddit 수집 중단 + RSS 수집 병렬화"
```

---

### Task 5: 짧은 요약에 대한 본문 fetch

**Files:**
- Modify: `sources/rss.py`
- Test: `tests/test_rss.py`

**Interfaces:**
- Produces: `enrich_with_body(items, max_fetch=MAX_BODY_FETCH) -> list[dict]` — 항목에 `"content"` 추가
- `main._add_summaries`가 `item.get(content_key) or item.get("content")` 순으로 보므로(main.py:21-22)
  `summary`가 짧아도 `content`가 채워지면 요약이 생성된다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_rss.py 에 추가
def test_enrich_fetches_body_only_for_short_summaries(monkeypatch):
    from sources import rss
    calls = []
    monkeypatch.setattr(rss, "_fetch_article_text",
                        lambda url, max_chars=2000: calls.append(url) or "본문 " * 200)
    items = [
        {"title": "짧음", "url": "http://a", "summary": "짧은 티저", "source": "s"},
        {"title": "충분", "url": "http://b", "summary": "가" * 300, "source": "s"},
    ]
    out = rss.enrich_with_body(items, max_fetch=10)
    assert calls == ["http://a"]
    assert len(out[0]["content"]) > 150
    assert "content" not in out[1]

def test_enrich_respects_max_fetch(monkeypatch):
    from sources import rss
    calls = []
    monkeypatch.setattr(rss, "_fetch_article_text",
                        lambda url, max_chars=2000: calls.append(url) or "x" * 400)
    items = [{"title": str(i), "url": f"http://{i}", "summary": "", "source": "s"} for i in range(10)]
    rss.enrich_with_body(items, max_fetch=3)
    assert len(calls) == 3

def test_enrich_ignores_html_tags_when_measuring():
    """<p><br/></p> 같은 껍데기는 150자를 넘어도 본문이 아니다"""
    from sources import rss
    assert rss._text_len("<p>" + "<br/>" * 60 + "</p>") < 150
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_rss.py -k enrich -v`
Expected: `AttributeError: module 'sources.rss' has no attribute 'enrich_with_body'`

- [ ] **Step 3: rss.py에 추가**

```python
import re
from sources.scraper import _fetch_article_text
from config import MAX_BODY_FETCH

_TAG = re.compile(r"<[^>]+>")
MIN_CONTENT = 150   # summarizer.summarize_item 이 요약을 포기하는 하한

def _text_len(html: str) -> int:
    return len(" ".join(_TAG.sub(" ", html or "").split()))

def enrich_with_body(items: list[dict], max_fetch: int = MAX_BODY_FETCH) -> list[dict]:
    """RSS 요약이 짧은 항목만 원문 본문을 받아 content 에 채운다.
    실측상 전체 엔트리의 45%가 150자 미만이라 이 단계 없이는 요약이 빈 문자열이 된다."""
    targets = [i for i in items if _text_len(i.get("summary", "")) < MIN_CONTENT][:max_fetch]
    if not targets:
        return items

    def one(item):
        body = _fetch_article_text(item["url"])
        if _text_len(body) >= MIN_CONTENT:
            item["content"] = body

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, targets))
    return items
```
`fetch_all_blogs()`의 마지막 줄을 `return enrich_with_body(all_items)`로 바꾼다.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_rss.py -v`
Expected: 전부 통과

- [ ] **Step 5: 실제 피드로 개선 효과 측정**

`scratchpad/verify_enrich.py`로 실제 소스 10개에 대해 보강 전후 "요약 가능(150자 이상)" 건수를 세어
출력하고, 그 수치를 커밋 메시지에 남긴다.

- [ ] **Step 6: 커밋**

```bash
git add sources/rss.py tests/test_rss.py
git commit -m "feat: RSS 요약이 짧을 때 원문 본문 fetch (요약 가능 55% -> N%)"
```

---

### Task 6: 날짜판정 + 제목번역 + 핵심요약을 LLM 호출 1회로 통합

**Files:**
- Modify: `summarizer.py:3-16,38-49`, `main.py:19-26,41-87`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Produces: `analyze_item(title, content, pub_hint, today) -> dict`
  반환: `{"is_today": bool, "pub_date": str, "title_ko": str, "summary": str}`.
  파싱 실패·호출 실패 시 `{"is_today": False, "pub_date": "unknown", "title_ko": "", "summary": ""}`.
- Produces: `main._analyze_items(items, content_key, filter_today=True) -> list[dict]`
  `filter_today=True`면 `is_today`가 False인 항목을 **리스트에서 제거**한다.
  arXiv·GitHub은 자체 날짜 체계가 있으므로 `filter_today=False`로 호출한다.
- `summarize_item`, `translate_title`은 남겨둔다 — 다른 호출부와 되돌리기를 위해.

**호출 비용:** 기존 항목당 2회(요약+번역) → **1회**. 대신 대상이 날짜 필터 통과분에서
전체 수집분(최대 63소스×3 + 스크래퍼 6 = 195건)으로 늘어난다. `content`는 1500자로 잘라 보낸다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_summarizer.py 에 추가
import json
from unittest.mock import patch
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
```

```python
# tests/test_main_collect.py 에 추가
def test_analyze_items_drops_non_today(monkeypatch):
    import main
    def fake(title, content, pub_hint, today):
        return {"is_today": pub_hint == "today", "pub_date": pub_hint,
                "title_ko": "한글", "summary": "요약"}
    monkeypatch.setattr(main, "analyze_item", fake)
    items = [
        {"title": "a", "summary": "가" * 300, "pub_hint": "today"},
        {"title": "b", "summary": "가" * 300, "pub_hint": "2026-01-01"},
    ]
    out = main._analyze_items(items, "summary")
    assert len(out) == 1 and out[0]["title"] == "a"
    assert out[0]["title_ko"] == "한글"

def test_analyze_items_keeps_all_when_filter_off(monkeypatch):
    import main
    monkeypatch.setattr(main, "analyze_item", lambda *a: {
        "is_today": False, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": "p", "abstract": "가" * 300}]
    out = main._analyze_items(items, "abstract", filter_today=False)
    assert len(out) == 1

def test_analyze_items_runs_in_parallel(monkeypatch):
    import time, main
    monkeypatch.setattr(main, "analyze_item", lambda *a: time.sleep(0.2) or {
        "is_today": True, "pub_date": "x", "title_ko": "한글", "summary": "요약"})
    items = [{"title": f"t{i}", "summary": "가" * 300, "pub_hint": "x"} for i in range(8)]
    t0 = time.monotonic()
    main._analyze_items(items, "summary")
    assert time.monotonic() - t0 < 1.0
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_summarizer.py tests/test_main_collect.py -v`
Expected: `AttributeError: module 'summarizer' has no attribute 'analyze_item'`

- [ ] **Step 3: summarizer.py에 통합 프롬프트/함수 추가**

```python
import json
import re

ANALYZE_PROMPT = """오늘은 {today} (KST)야.
아래 글이 오늘 발행된 글인지 판단하고, 오늘 글이면 제목을 번역하고 핵심을 정리해줘.

[발행일 정보]: {pub_hint}
[제목]: {title}
[내용]: {content}

아래 JSON 형식으로만 답해. 설명이나 마크다운 없이 JSON만.
{{"is_today": true 또는 false, "pub_date": "YYYY-MM-DD 또는 unknown", "title_ko": "", "summary": ""}}

규칙:
- [발행일 정보]가 오늘 날짜면 is_today 는 true. 다른 날짜면 false.
- [발행일 정보]가 unknown 이면 [내용]에서 발행일을 찾아봐. 그래도 확인 안 되면 false.
- is_today 가 false 면 title_ko 와 summary 는 빈 문자열로 두고 끝내.
- title_ko: 제목을 자연스러운 한국어로. 고유명사(제품명·회사명·기술명)는 그대로 둬.
  제목이 이미 한국어면 그대로 써.
- summary: 첫 줄에 무엇에 관한 글인지 한 줄, 그 다음 핵심 3가지를 각각 "- "로 시작하는 줄로.
  반드시 [내용]에 있는 정보만 사용해. 추가 지식이나 추론으로 만들어내지 마.
  배경 설명·일반론은 빼고 이 글에만 있는 구체적인 사실·수치·기법을 골라.
  [내용]이 불충분하면 빈 문자열.
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_JSON_OBJ = re.compile(r"\{.*\}", re.S)
_SAFE_DEFAULT = {"is_today": False, "pub_date": "unknown", "title_ko": "", "summary": ""}

def analyze_item(title: str, content: str, pub_hint: str, today: str) -> dict:
    """날짜 판정 + 제목 번역 + 핵심 요약을 claude 호출 한 번으로 처리한다."""
    raw = _run_claude(ANALYZE_PROMPT.format(
        today=today, pub_hint=pub_hint or "unknown",
        title=title, content=(content or "")[:1500]), timeout=120)
    if not raw:
        return dict(_SAFE_DEFAULT)
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    m = _JSON_OBJ.search(text)
    if not m:
        return dict(_SAFE_DEFAULT)
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return dict(_SAFE_DEFAULT)
    return {
        "is_today": bool(data.get("is_today")),
        "pub_date": str(data.get("pub_date") or "unknown"),
        "title_ko": str(data.get("title_ko") or ""),
        "summary": str(data.get("summary") or ""),
    }
```

- [ ] **Step 4: main.py의 요약 단계 교체**

```python
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from config import SUMMARY_WORKERS, MAX_COMPANY_TOTAL, MAX_DEV_TOTAL
from summarizer import analyze_item, filter_important_papers, generate_highlights

def _analyze_items(items: list[dict], content_key: str, filter_today: bool = True) -> list[dict]:
    """날짜 판정·제목 번역·요약을 항목당 claude 호출 1회로 처리하고,
    오늘 글이 아닌 항목은 리스트에서 제외한다."""
    if not items:
        return items
    today = str(date.today())

    def one(item):
        content = (item.get(content_key) or item.get("content") or
                   item.get("description") or item.get("abstract") or "")
        title = item.get("title") or item.get("name", "")
        result = analyze_item(title, content, item.get("pub_hint", "unknown"), today)
        item["summary"] = result["summary"]
        item["title_ko"] = result["title_ko"]
        item["pub_date"] = result["pub_date"]
        item["is_today"] = result["is_today"]
        return item

    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as ex:
        analyzed = list(ex.map(one, items))
    if not filter_today:
        return analyzed
    kept = [i for i in analyzed if i.get("is_today")]
    print(f"  [날짜판정] {len(analyzed)}건 중 오늘 글 {len(kept)}건")
    return kept
```

`summarize()`를 교체한다. **상한은 날짜 판정 뒤에 적용**한다 — 판정 전에 자르면 오늘 글이 잘려나간다:
```python
def summarize(data: dict) -> dict:
    print("[분석] 날짜판정 + 요약 시작")
    data["company_blogs"] = _analyze_items(data["company_blogs"], "summary")[:MAX_COMPANY_TOTAL]
    data["dev_blogs"] = _analyze_items(data["dev_blogs"], "summary")[:MAX_DEV_TOTAL]
    data["papers"] = _analyze_items(data["papers"], "abstract", filter_today=False)
    data["github"] = _analyze_items(data["github"], "readme", filter_today=False)
    data["highlights"] = generate_highlights(data)
    return data
```
`_add_summaries`는 삭제한다.

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과

- [ ] **Step 6: 실제 호출 1건으로 JSON 형식 확인**

Run:
```bash
.venv/bin/python -c "
from summarizer import analyze_item
print(analyze_item('Test Article About Caching', '본문 '*300, '2026-08-14 09:00 KST', '2026-08-14'))
print(analyze_item('Old Article', '본문 '*300, '2026-01-02 09:00 KST', '2026-08-14'))
"
```
Expected: 첫 번째는 `is_today=True` + 요약 있음, 두 번째는 `is_today=False` + 빈 요약.
출력을 보고에 남긴다. 형식이 안 맞으면 프롬프트를 조정한다.

- [ ] **Step 7: 커밋**

```bash
git add summarizer.py main.py tests/test_summarizer.py tests/test_main_collect.py
git commit -m "feat: 날짜판정+제목번역+핵심요약을 LLM 호출 1회로 통합, 오늘 글 아니면 제외"
```

---

### Task 7: 개념 SVG 생성 + 검증/새니타이즈

**Files:**
- Create: `svgmaker.py`
- Modify: `main.py` (summarize 단계)
- Test: `tests/test_svgmaker.py`

**Interfaces:**
- Produces: `sanitize_svg(raw) -> str` — 안전한 SVG 또는 `""`
- Produces: `generate_concept_svg(title, content) -> str`
- Produces: `add_svgs(items, max_items) -> list[dict]` — 항목에 `"svg"` 추가
- 소비처: `renderer._item_html`이 `item.get("svg","")`를 **이스케이프 없이** 삽입한다.

**보안 요건:** stdlib `xml.etree.ElementTree`는 billion-laughs/XXE에 취약하다. 새 의존성(defusedxml)을
추가하지 않는 제약이 있으므로, **파싱 전에 `<!DOCTYPE`·`<!ENTITY`·`<?xml-stylesheet`가 있으면 즉시 거부**하고
입력 길이를 제한한다. 엔티티 정의가 없으면 확장 공격이 성립하지 않는다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_svgmaker.py
import svgmaker

def test_rejects_non_svg():
    assert svgmaker.sanitize_svg("이건 SVG가 아닙니다") == ""
    assert svgmaker.sanitize_svg("") == ""

def test_rejects_malformed_xml():
    assert svgmaker.sanitize_svg('<svg><rect width="10"></svg>') == ""

def test_rejects_doctype_and_entities():
    """billion laughs 방어 — 엔티티 정의가 보이면 파싱조차 하지 않는다"""
    bomb = ('<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">]>'
            '<svg xmlns="http://www.w3.org/2000/svg"><text>&a;</text></svg>')
    assert svgmaker.sanitize_svg(bomb) == ""

def test_rejects_oversized_input():
    assert svgmaker.sanitize_svg("<svg>" + "x" * 200000 + "</svg>") == ""

def test_strips_script_and_event_handlers():
    raw = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<script>alert(1)</script>'
           '<rect width="50" height="50" onclick="steal()"/></svg>')
    out = svgmaker.sanitize_svg(raw)
    assert out != "" and "script" not in out.lower() and "onclick" not in out.lower()
    assert "<rect" in out

def test_strips_external_refs():
    raw = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<image href="https://evil.example/x.png"/><rect width="5" height="5"/></svg>')
    assert "evil.example" not in svgmaker.sanitize_svg(raw)

def test_extracts_svg_from_markdown_fence():
    raw = '```svg\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="5" height="5"/></svg>\n```'
    assert svgmaker.sanitize_svg(raw).startswith("<svg")

def test_keeps_valid_svg():
    raw = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<rect x="10" y="10" width="80" height="40" fill="#eee"/>'
           '<text x="20" y="35">Client</text></svg>')
    out = svgmaker.sanitize_svg(raw)
    assert "<text" in out and "Client" in out

def test_add_svgs_respects_max(monkeypatch):
    calls = []
    monkeypatch.setattr(svgmaker, "generate_concept_svg",
                        lambda t, c: calls.append(t) or "<svg/>")
    items = [{"title": str(i), "summary": "가" * 300} for i in range(10)]
    svgmaker.add_svgs(items, max_items=3)
    assert len(calls) == 3

def test_add_svgs_skips_items_without_content(monkeypatch):
    monkeypatch.setattr(svgmaker, "generate_concept_svg", lambda t, c: "<svg/>")
    items = [{"title": "빈 요약", "summary": ""}]
    svgmaker.add_svgs(items, max_items=5)
    assert items[0].get("svg", "") == ""
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_svgmaker.py -v`
Expected: `ModuleNotFoundError: No module named 'svgmaker'`

- [ ] **Step 3: svgmaker.py 구현**

```python
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from summarizer import _run_claude

SVG_PROMPT = """아래 글의 핵심 개념을 한눈에 이해할 수 있는 다이어그램을 SVG로 그려줘.

규칙:
- 순수 SVG 코드만 출력해. 설명, 마크다운 펜스 없이.
- 루트는 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 320">
- width/height 속성은 넣지 마 (반응형으로 쓸 거야)
- 구조·흐름·관계를 박스와 화살표로 표현해. 장식은 최소로.
- 글자는 한국어로, font-size 는 13 이상.
- 색은 #1a1714(선/글자), #e05c1a(강조), #f5f2ee(배경 박스) 만 사용해.
- script, 이벤트 핸들러, 외부 이미지 참조, DOCTYPE 은 절대 넣지 마.
- 내용에서 확인되지 않는 개념을 지어내지 마. 그릴 게 없으면 NONE 만 출력해.

제목: {title}
내용: {content}
SVG:"""

MAX_SVG_CHARS = 100_000
_FENCE = re.compile(r"```(?:svg|xml)?\s*(.*?)```", re.S)
_SVG_TAG = re.compile(r"<svg\b.*?</svg>", re.S | re.I)
_UNSAFE_PROLOG = re.compile(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", re.I)
_DANGEROUS_TAGS = {"script", "foreignobject", "iframe", "use", "image", "animate", "set", "handler"}
_URL_ATTRS = {"href", "{http://www.w3.org/1999/xlink}href", "xlink:href", "src"}


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1].lower() if "}" in tag else str(tag).lower()


def sanitize_svg(raw: str) -> str:
    """모델이 만든 SVG를 검증하고 위험 요소를 제거한다.
    페이지에 이스케이프 없이 삽입되므로 조금이라도 이상하면 빈 문자열을 돌려준다."""
    if not raw or not raw.strip() or len(raw) > MAX_SVG_CHARS:
        return ""
    text = raw.strip()
    if _UNSAFE_PROLOG.search(text):
        return ""
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    m = _SVG_TAG.search(text)
    if not m:
        return ""
    text = m.group(0)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ""
    if _strip_ns(root.tag) != "svg":
        return ""

    def clean(node) -> bool:
        if _strip_ns(node.tag) in _DANGEROUS_TAGS:
            return False
        for attr in list(node.attrib):
            low = attr.lower()
            if low.startswith("on") or low in _URL_ATTRS:
                del node.attrib[attr]
        for child in list(node):
            if not clean(child):
                node.remove(child)
        return True

    clean(root)
    root.set("xmlns", "http://www.w3.org/2000/svg")
    for junk in ("width", "height"):
        root.attrib.pop(junk, None)
    if root.get("viewBox") is None:
        root.set("viewBox", "0 0 640 320")
    out = ET.tostring(root, encoding="unicode")
    out = out.replace('xmlns:ns0="http://www.w3.org/2000/svg"', "").replace("ns0:", "")
    return out if out.startswith("<svg") and len(out) > 40 else ""


def generate_concept_svg(title: str, content: str) -> str:
    if not content or len(content.strip()) < 150:
        return ""
    raw = _run_claude(SVG_PROMPT.format(title=title, content=content[:2000]), timeout=120)
    if not raw or raw.strip().upper().startswith("NONE"):
        return ""
    return sanitize_svg(raw)


def add_svgs(items: list[dict], max_items: int) -> list[dict]:
    targets = [i for i in items if len((i.get("summary") or "").strip()) >= 150][:max_items]
    if not targets:
        return items

    def one(item):
        item["svg"] = generate_concept_svg(item.get("title", ""), item.get("summary", ""))

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(one, targets))
    return items
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_svgmaker.py -v`
Expected: 10 passed

- [ ] **Step 5: main.summarize에 연결**

```python
from config import ENABLE_SVG, MAX_SVG_ITEMS
from svgmaker import add_svgs

# summarize() 안, 요약이 끝난 뒤
if ENABLE_SVG:
    print("[SVG] 생성 중...")
    add_svgs(data["company_blogs"], MAX_SVG_ITEMS)
    add_svgs(data["dev_blogs"], MAX_SVG_ITEMS)
```

- [ ] **Step 6: 실제 모델로 SVG 1건 생성해 눈으로 확인**

`scratchpad/try_svg.py`로 실제 글 1건의 SVG를 만들어 파일로 저장하고 브라우저에서 본다.
깨지면 프롬프트를 조정한다. 자동 테스트로 대체 불가.

- [ ] **Step 7: 커밋**

```bash
git add svgmaker.py main.py tests/test_svgmaker.py
git commit -m "feat: 글 핵심 개념 SVG 생성 (XML 검증 + 새니타이즈)"
```

---

### Task 8: 아코디언 UI

**Files:**
- Modify: `renderer.py:149-158` (`_item_html`), `renderer.py:23-76` (`_DAILY_CSS`), `renderer.py:200-226`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Produces: `_item_html(name, url, meta, summary, name_ko="", svg="")` — 인자를 뒤에 추가해 기존 호출 호환

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_renderer.py 에 추가
def test_item_is_collapsible():
    from renderer import _item_html
    html = _item_html("Title", "http://x", "meta", "요약 본문", "한글제목")
    assert "<details" in html and "<summary" in html and "한글제목" in html

def test_collapsed_by_default():
    from renderer import _item_html
    assert "<details open" not in _item_html("T", "http://x", "m", "본문", "")

def test_svg_is_embedded_raw_not_escaped():
    from renderer import _item_html
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="5" height="5"/></svg>'
    html = _item_html("T", "http://x", "m", "본문", "", svg)
    assert "<svg" in html and "&lt;svg" not in html

def test_summary_is_still_escaped():
    from renderer import _item_html
    html = _item_html("T", "http://x", "m", "<script>alert(1)</script>", "")
    assert "<script>" not in html and "&lt;script&gt;" in html

def test_item_without_summary_has_no_toggle():
    from renderer import _item_html
    assert "<details" not in _item_html("T", "http://x", "m", "", "")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_renderer.py -k "collapsible or collapsed or svg or escaped or toggle" -v`
Expected: 전부 FAIL

- [ ] **Step 3: `_item_html` 재작성**

```python
def _item_html(name: str, url: str, meta: str, summary: str,
               name_ko: str = "", svg: str = "") -> str:
    display_name = name_ko if name_ko and name_ko.strip() else name
    link_html = f'<a href="{url}" target="_blank" rel="noopener">{_e(display_name)}</a>'
    has_body = bool((summary or "").strip()) or bool((svg or "").strip())

    if not has_body:
        return f"""<div class="item">
  <div class="item-head">
    <div class="item-name">{link_html}</div>
    <div class="item-meta">{_e(meta)}</div>
  </div>
</div>"""

    body = ""
    if svg and svg.strip():
        body += f'<div class="item-diagram">{svg}</div>'
    if summary and summary.strip():
        body += f'<div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>'

    return f"""<div class="item">
  <details>
    <summary>
      <span class="item-name">{_e(display_name)}</span>
      <span class="item-meta">{_e(meta)}</span>
      <span class="item-toggle" aria-hidden="true"></span>
    </summary>
    <div class="item-body">
      {body}
      <div class="item-link">{link_html} &rarr;</div>
    </div>
  </details>
</div>"""
```

제목 링크를 `<summary>` 안에 두면 클릭이 펼침과 충돌하므로, 헤더에는 텍스트만 두고 본문 하단에 원문 링크를 둔다.

- [ ] **Step 4: CSS 교체**

`_DAILY_CSS`의 `.item` 블록(renderer.py:59-70)을 아코디언용으로 교체한다:
```css
  .item { border-bottom: 1px solid var(--rule); }
  .item:last-child { border-bottom: none; }
  .item details > summary { display: grid; grid-template-columns: 1fr auto auto;
    gap: 0.8rem; align-items: baseline; padding: 1rem 0; cursor: pointer; list-style: none; }
  .item details > summary::-webkit-details-marker { display: none; }
  .item details > summary:hover .item-name { color: var(--accent-deep); }
  .item-name { font-weight: 600; font-size: 0.97rem; line-height: 1.4; color: var(--ink); }
  .item-name a { color: var(--ink); text-decoration: none; }
  .item-name a:hover { color: var(--accent-deep); }
  .item-meta { font-family: var(--mono); font-size: 0.63rem; color: var(--ink-faint);
    letter-spacing: 0.04em; white-space: nowrap; }
  .item-toggle::before { content: "+"; font-family: var(--mono); font-size: 0.9rem; color: var(--ink-faint); }
  .item details[open] > summary .item-toggle::before { content: "\2212"; color: var(--accent); }
  .item-body { padding: 0 0 1.2rem; }
  .item-summary { font-size: 0.875rem; color: var(--ink-soft); line-height: 1.7; }
  .item-diagram { margin: 0 0 1rem; padding: 1rem; background: var(--paper-deep);
    border: 1px solid var(--rule); overflow-x: auto; }
  .item-diagram svg { max-width: 100%; height: auto; display: block; }
  .item-link { margin-top: 0.9rem; font-family: var(--mono); font-size: 0.7rem; }
  .item-link a { color: var(--accent-deep); text-decoration: none; }
  .item-head { padding: 1rem 0; }
```

- [ ] **Step 5: 섹션 호출부에 svg 전달**

`renderer.py:200-208`의 company_blogs / dev_blogs 렌더 호출에 `i.get("svg","")` 인자를 추가한다.
논문·GitHub 섹션은 SVG 대상이 아니므로 그대로 둔다.

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add renderer.py tests/test_renderer.py
git commit -m "feat: 아코디언 UI — 제목만 노출, 클릭 시 요약/다이어그램 펼침"
```

---

### Task 9: 로컬 실행 + 결과 확인

**Files:**
- Create: `scratchpad/run_local.py` (커밋하지 않음)

- [ ] **Step 1: 로컬 실행 드라이버 작성**

`main.main()`은 끝에서 `git_commit_push()`로 **push까지 한다**(main.py:170-178). 확인용으로 쓰면 안 된다.

```python
# scratchpad/run_local.py
import sys
sys.path.insert(0, "/Users/kimeunmi/source/study/trending-tech")
from datetime import date
import main
from renderer import render_daily_page

today = str(date.today())
data = main.collect(today)
data = main.summarize(data)
open(sys.argv[1], "w", encoding="utf-8").write(render_daily_page(data))
print("항목수:", {k: len(v) for k, v in data.items() if isinstance(v, list)})
print("요약 있는 항목:", sum(1 for k in ("company_blogs", "dev_blogs", "papers")
                          for i in data[k] if i.get("summary")))
print("SVG 있는 항목:", sum(1 for k in ("company_blogs", "dev_blogs")
                        for i in data[k] if i.get("svg")))
```

- [ ] **Step 2: 실행**

Run: `.venv/bin/python scratchpad/run_local.py scratchpad/preview.html`
Expected: 항목수/요약/SVG 카운트 출력 + HTML 생성

- [ ] **Step 3: 전체 테스트 재실행**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 통과 — 출력을 그대로 보고에 붙인다

- [ ] **Step 4: 결과 전달**

`SendUserFile`로 `scratchpad/preview.html` 전달. GitHub Pages 링크는 push가 필요하므로
**사용자에게 별도 확인을 받은 뒤에만** 진행한다.

---

## Self-Review

**스펙 커버리지**
- 블로그 목록 추가 → Task 3
- HN/Reddit 제거 → Task 4
- Alibaba 요약 없음 → Task 2(상위 3건·발행일 힌트), Task 5(본문 보강). RSS 전환은 **불가**(RSS 미제공 실측)
- 날짜 판정을 LLM으로 → Task 1·2(힌트 수집), Task 6(판정+제외)
- 요약과 날짜 판정을 한 번의 호출로 → Task 6 (`analyze_item`, 항목당 2회 → 1회)
- 오늘 글 아니면 리스트에서 제외 → Task 6 (`_analyze_items(filter_today=True)`)
- 소스당 최신 3건만 → Task 1, 2, 3
- 비용/시간 → Task 4(수집 병렬), Task 6(분석 병렬·상한)
- 핵심 내용 요약 → Task 6
- 개념 SVG → Task 7
- 아코디언 → Task 8
- 실행 후 결과 → Task 9

**알려진 트레이드오프**
- 소스당 3건 제한 → Cloudflare·AWS·GitHub Blog처럼 하루 4건 이상 올리는 곳은 나머지가 누락된다.
- 날짜 판정을 LLM에 맡기면 **호출 대상이 늘어난다.** 기존에는 날짜 필터를 통과한 소수(8/13 기준 15건)만
  LLM에 보냈지만, 이제 수집분 전체(최대 195건)를 보낸다. 항목당 호출은 2회→1회로 줄지만
  총 호출 수는 늘어난다. `content`를 1500자로 자르고 병렬 4로 돌려 완화한다.
- RSS의 `pubDate`는 기계가 읽는 정확한 값인데 LLM 판정을 최종으로 두면 정확도가 내려갈 수 있다.
  파싱된 KST 날짜를 `pub_hint`로 함께 넘겨 근거 없는 추측을 막는다.
- `category`가 company/dev 2종뿐이라 사용자가 준 7개 그룹 구분은 페이지에 반영되지 않는다.

**보고 대상**
- RSS 미제공으로 추가 못 한 소스: Anthropic, LinkedIn, Shopify, DoorDash, 우아한형제들, RIDI,
  NAVER CLOVA, OpenSource Connections, deepset, mlops.systems, Made With ML,
  Full Stack Deep Learning, MLOps Community, Alex Petrov, Geoffrey Hinton, ABLY
- Medium rate limit(429)으로 미검증: 당근, Coupang — URL 패턴은 유효하므로 추가하되 실패 시 로그로 확인
- 판독 불가 항목: `Ethg)` — 무엇인지 확인 필요
- 오래된 피드(최신 글 1년 이상 경과): Chris Olah(2019), Mike McCandless(2021), Ben Frederickson(2021),
  DBMS Musings(2021), Cindy Sridharan(2022), 직방(2023), Sam Newman(2023), François Chollet(2023),
  Nils Reimers(2022), 29CM(2025-06), Chip Huyen(2025-01), Jay Alammar(2025-03),
  Yoshua Bengio(2025-06), Martin Kleppmann(2025-12)
