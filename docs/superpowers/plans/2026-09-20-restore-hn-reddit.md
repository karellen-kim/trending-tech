# Hacker News + Reddit 수집 복원 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-08-14 커밋 `ca06ffe` 에서 빠진 HN·Reddit 수집을 되살리되, 둘을 번갈아 섞어 상위 5건만 싣는다.

**Architecture:** `collect()` 가 기존 ThreadPoolExecutor 에 HN·Reddit 수집을 다시 넣고, 두 결과를 번갈아 뽑아 5건으로 자른 뒤 `data["community"]` 에 담는다. 렌더러는 이미 "Hacker News & Reddit" 섹션(`renderer.py:310`)을 갖고 있으므로 데이터 키만 연결한다.

**Tech Stack:** Python 3.10, requests, feedparser, pytest

**Spec:** 이 대화의 사용자 지시 — "빠졌다면 지금부터 추가해줘, 해커뉴스 레딧 합쳐서 상위 5개만", 정렬은 번갈아 섞기, HN 수집 방식은 `front_page` 유지.

## Global Constraints

- 기존 코드 스타일 유지. 요청하지 않은 리팩토링·타입 어노테이션 추가 금지.
- HN 수집 방식은 현행 유지 — `tags=front_page`, `hitsPerPage=MAX_HN_ITEMS`(10). 검색 기반으로 바꾸지 않는다.
- 커뮤니티 상한은 HN·Reddit **합산 5건**.
- 한 소스가 죽어도 배치는 계속된다 (notebooklm 단계와 같은 원칙).
- Reddit RSS 에는 점수가 없다. 두 소스를 한 기준으로 정렬하지 않고 각 소스의 원래 순위를 유지한 채 번갈아 섞는다.

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `config.py` | 수집 상한 상수 | `MAX_COMMUNITY_ITEMS = 5` 추가 |
| `main.py` | 수집 오케스트레이션 | import 2줄, `_merge_community()` 신규, `collect()` 배선, `summarize()` 1줄 |
| `renderer.py` | 일별 페이지 렌더 | 335행 데이터 키에 `community` 폴백 추가 |
| `tests/test_main_collect.py` | collect 단계 테스트 | 기존 테스트 1건 교체 + 신규 3건 |

`sources/hackernews.py`, `sources/reddit.py` 는 그대로 쓴다. 두 파일 모두 현재 정상 동작하는 것을 실측 확인했다(r/LocalLLaMA 5건 수집).

---

### Task 1: 병합 헬퍼

**Files:**
- Modify: `config.py:38-43` (상수 블록)
- Modify: `main.py:1-24` (import), `main.py:26` 앞 (헬퍼 추가)
- Test: `tests/test_main_collect.py`

**Interfaces:**
- Produces: `main._merge_community(hn: list[dict], reddit: list[dict], limit: int = MAX_COMMUNITY_ITEMS) -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_main_collect.py` 상단 `import main` 아래에 추가:

```python
def test_merge_community_interleaves_and_caps():
    """Reddit RSS 에는 점수가 없어 한 기준으로 정렬할 수 없다. 번갈아 섞는다."""
    hn = [{"title": f"h{i}"} for i in range(4)]
    rd = [{"title": f"r{i}"} for i in range(4)]
    out = main._merge_community(hn, rd, limit=5)
    assert [i["title"] for i in out] == ["h0", "r0", "h1", "r1", "h2"]


def test_merge_community_fills_from_one_side():
    """한쪽이 비어도 5건을 채운다"""
    out = main._merge_community([], [{"title": f"r{i}"} for i in range(7)], limit=5)
    assert [i["title"] for i in out] == ["r0", "r1", "r2", "r3", "r4"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -k merge_community -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute '_merge_community'`

- [ ] **Step 3: 구현**

`config.py` 의 `MAX_SCRAPER_ITEMS = 3` 아래에 추가:

```python
MAX_COMMUNITY_ITEMS = 5   # HN + Reddit 합산 상한
```

`main.py` import 수정:

```python
from itertools import zip_longest
```
(기존 `from concurrent.futures import ThreadPoolExecutor` 아래)

```python
from config import (DOCS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS, SUMMARY_WORKERS, now_kst,
                    MAX_COMMUNITY_ITEMS, MAX_COMPANY_TOTAL, MAX_DEV_TOTAL, ENABLE_SVG,
                    MAX_SVG_ITEMS, ENABLE_NOTEBOOKLM)
from sources.github import fetch_trending
from sources.hackernews import fetch_top_stories
from sources.reddit import fetch_all_reddit
```

`_analyze_items` 정의 앞에 헬퍼 추가:

```python
def _merge_community(hn: list[dict], reddit: list[dict],
                     limit: int = MAX_COMMUNITY_ITEMS) -> list[dict]:
    """HN·Reddit 을 번갈아 뽑아 상위 limit 건만 남긴다.
    Reddit RSS 에는 점수가 없어 두 소스를 한 기준으로 정렬할 수 없다.
    각 소스의 원래 순위를 유지한 채 섞는다."""
    merged = []
    for pair in zip_longest(hn, reddit):
        for item in pair:
            if item and len(merged) < limit:
                merged.append(item)
    return merged
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -k merge_community -v`
Expected: PASS 2건

- [ ] **Step 5: 커밋**

```bash
git add config.py main.py tests/test_main_collect.py
git commit -m "feat: HN+Reddit 병합 헬퍼 추가"
```

---

### Task 2: collect() 배선

**Files:**
- Modify: `main.py:89-126` (`collect`)
- Test: `tests/test_main_collect.py:5-13` (기존 테스트 교체)

**Interfaces:**
- Consumes: `main._merge_community` (Task 1)
- Produces: `collect()` 반환 dict 에 `"community": list[dict]` 키

- [ ] **Step 1: 기존 테스트를 새 동작으로 교체**

`tests/test_main_collect.py` 의 `test_collect_excludes_hn_and_reddit` 을 통째로 아래로 바꾼다. 이 테스트는 08-14 에 수집을 뺀 상태를 고정하던 것이라 이제 유효하지 않다.

```python
def test_collect_merges_community_into_five():
    """HN·Reddit 을 합쳐 5건만 싣는다"""
    hn = [{"title": f"h{i}", "url": f"http://h{i}", "points": 10} for i in range(4)]
    rd = [{"title": f"r{i}", "url": f"http://r{i}", "source": "r/x"} for i in range(4)]
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", return_value=hn), \
         patch("main.fetch_all_reddit", return_value=rd), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-09-20")
    assert [i["title"] for i in data["community"]] == ["h0", "r0", "h1", "r1", "h2"]


def test_collect_survives_hn_failure():
    """한 소스가 죽어도 배치는 계속된다"""
    rd = [{"title": "r0", "url": "http://r0", "source": "r/x"}]
    with patch("main.fetch_trending", return_value=[]), \
         patch("main.fetch_all_blogs", return_value=[]), \
         patch("main.fetch_all_papers", return_value=[]), \
         patch("main.fetch_all_scraped", return_value=[]), \
         patch("main.fetch_top_stories", side_effect=RuntimeError("HN 503")), \
         patch("main.fetch_all_reddit", return_value=rd), \
         patch("main.filter_important_papers", return_value=[]):
        data = main.collect("2026-09-20")
    assert [i["title"] for i in data["community"]] == ["r0"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -k collect -v`
Expected: FAIL — `AttributeError: <module 'main'> does not have the attribute 'fetch_top_stories'`

- [ ] **Step 3: 구현**

`main.py` 의 `collect()` 를 수정한다. executor 블록:

```python
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_gh = ex.submit(fetch_trending, "daily", yesterday_github)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        f_sc = ex.submit(fetch_all_scraped)
        f_hn = ex.submit(fetch_top_stories)
        f_rd = ex.submit(fetch_all_reddit)
        github = f_gh.result()
        all_blogs = f_bl.result()
        papers = f_ar.result()
        scraped = f_sc.result()
        try:
            hn = f_hn.result()
        except Exception as e:
            print(f"[HN] 수집 실패: {e}")
            hn = []
        try:
            reddit = f_rd.result()
        except Exception as e:
            print(f"[Reddit] 수집 실패: {e}")
            reddit = []
```

`papers = filter_important_papers(...)` 아래에 추가:

```python
    community = _merge_community(hn, reddit)
```

print 문과 반환 dict:

```python
    print(f"  GitHub:{len(github)} Company:{len(company_blogs)} "
          f"Dev:{len(dev_blogs)} Papers:{len(papers)} Community:{len(community)}")

    return {
        "date": today,
        "github": github,
        "company_blogs": company_blogs,
        "dev_blogs": dev_blogs,
        "papers": papers,
        "community": community,
    }
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -v`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add main.py tests/test_main_collect.py
git commit -m "feat: collect 에 HN+Reddit 복원"
```

---

### Task 3: 요약 연결 + 렌더러 키

**Files:**
- Modify: `main.py:129-135` (`summarize`)
- Modify: `renderer.py:335`
- Test: `tests/test_main_collect.py`

**Interfaces:**
- Consumes: `collect()` 의 `data["community"]` (Task 2)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_summarize_translates_community(monkeypatch):
    """커뮤니티 항목도 제목 번역·요약을 거친다. 날짜 판정은 하지 않는다."""
    got = {}
    monkeypatch.setattr(main, "analyze_item",
                        lambda t, c, p, d, date_verified=False: got.update(
                            title=t, verified=date_verified) or {
                            "is_today": False, "pub_date": "x",
                            "title_ko": "한글제목", "summary": "요약"})
    monkeypatch.setattr(main, "ENABLE_SVG", False)
    monkeypatch.setattr(main, "generate_today_take", lambda d: {})
    monkeypatch.setattr(main, "generate_highlight_links", lambda d: [])
    monkeypatch.setattr(main, "generate_highlights", lambda d: [])
    data = main.summarize({"date": "2026-09-20", "company_blogs": [], "dev_blogs": [],
                           "papers": [], "github": [],
                           "community": [{"title": "Jev is not an LLM", "url": "http://a"}]})
    assert data["community"][0]["title_ko"] == "한글제목"
    assert got["verified"] is True, "날짜 판정을 태우면 요약이 빈 값이 된다"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_main_collect.py -k summarize_translates -v`
Expected: FAIL — `KeyError: 'title_ko'` (community 를 분석하지 않아 그대로 통과함)

- [ ] **Step 3: 구현**

`main.py` `summarize()` 의 `data["github"] = ...` 줄 아래에 추가:

```python
    # 커뮤니티는 제목만 있는 항목이라 제목으로 번역·요약한다. 날짜는 수집 단계에서 이미 걸렀다.
    data["community"] = _analyze_items(data["community"], "title", filter_today=False)
```

`renderer.py:335` 를 수정한다. 옛 페이지 재생성(`restyle_old_pages.py:29` 가 `hn` 키를 쓴다)을 깨지 않도록 폴백을 남긴다:

```python
    hn_reddit = data.get("community") or (data.get("hn", []) + data.get("reddit", []))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add main.py renderer.py tests/test_main_collect.py
git commit -m "feat: 커뮤니티 섹션 요약·렌더 연결"
```

---

### Task 4: 실제 배치로 검증

**Files:** 없음 (실행 검증만)

- [ ] **Step 1: DRY 배치 실행**

```bash
DRY=1 .venv/bin/python main.py
```

- [ ] **Step 2: 수집 로그 확인**

Expected: `Community:5` (HN·Reddit 모두 살아 있을 때). 0 이면 두 소스 모두 실패한 것이므로 `[HN] 수집 실패` / `[Reddit] 수집 실패` 줄을 확인한다.

- [ ] **Step 3: 페이지 확인**

```bash
grep -c -E 'reddit\.com|news\.ycombinator' docs/$(date +%Y-%m-%d).html
```

Expected: 1 이상. `hn-reddit` 섹션이 nav 에도 나타나야 한다.

- [ ] **Step 4: 커밋**

DRY 실행으로 생성된 `docs/` 산출물은 커밋하지 않는다. 정규 배치(23:55)가 덮어쓴다.

## 한계

- **Jev 같은 신생 주제는 이 변경으로도 대부분 안 잡힌다.** HN 은 `front_page` 만 보는데 현재 Jev 관련 글은 1~3점이라 프런트페이지에 없다. Reddit 은 당일 상위글에 들어야 하고, 합산 5건 상한이 더해져 확률이 낮아진다. 신생 주제 포착이 목표라면 HN 을 `search_by_date` + 점수 하한으로 바꾸는 별도 변경이 필요하다.
- 합산 5건은 08-14 이전(서브레딧 6개 × 5건 = 최대 30건)보다 훨씬 좁다. 사용자 지시에 따른 것이다.
