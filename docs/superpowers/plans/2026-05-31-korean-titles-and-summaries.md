# Korean Titles & Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영어 제목을 한국어로 번역하고, 스크래퍼 항목에도 한국어 요약을 생성한다.

**Architecture:** `summarizer.py`에 title 번역 함수 추가, `scraper.py`에 기사 본문 fetch 추가, `renderer.py`가 `title_ko` 우선 표시. `main.py` 파이프라인에 번역 단계 삽입. 버그(제목 앞 글자 잘림)도 함께 수정.

**Tech Stack:** Python 3.10+, subprocess claude CLI, requests, BeautifulSoup

---

## 문제 요약

1. `item-name`에 영어 제목만 표시됨 → `title_ko` 필드 추가 필요
2. `item-summary`가 비어있음 → scraper 항목은 `summary:""`이라 `summarize_item()` 조건(150자) 미달
3. scraper.py `_strip_category_prefix` 버그 → `^[A-Z]{2,}` 정규식이 "ABcd" 패턴에서 'A' 하나만 남기는 경우 발생 (e.g. "pache Hudi", "oirai")

---

### Task 1: `summarizer.py` — 제목 번역 함수 추가

**Files:**
- Modify: `summarizer.py`

- [ ] **Step 1: translate_title 함수 추가**

```python
TRANSLATE_TITLE_PROMPT = """다음 영어 제목을 자연스러운 한국어로 번역해줘.
규칙: 번역문만 출력해. 설명, 부연, 따옴표 없이.
고유명사(제품명, 회사명, 기술명)는 그대로 유지해.

제목: {title}
번역:"""

def translate_title(title: str) -> str:
    if not title or not title.strip():
        return title
    # ASCII 비율이 낮으면(한국어 등) 이미 번역된 것으로 간주
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / max(len(title), 1)
    if ascii_ratio < 0.6:
        return title
    return _run_claude(TRANSLATE_TITLE_PROMPT.format(title=title), timeout=30)
```

- [ ] **Step 2: 확인**

```bash
cd /Users/kimeunmi/source/project/trending-tech
.venv/bin/python -c "from summarizer import translate_title; print(translate_title('SQLite is all you need for durable workflows'))"
```
Expected: 한국어 출력 (예: "SQLite만으로 내구성 있는 워크플로우 구현 가능")

---

### Task 2: `sources/scraper.py` — 기사 본문 fetch 추가 + 버그 수정

**Files:**
- Modify: `sources/scraper.py`

- [ ] **Step 1: `_strip_category_prefix` 버그 수정**

현재 코드:
```python
def _strip_category_prefix(text: str) -> str:
    return re.sub(r'^[A-Z]{2,}', '', text).strip()
```

수정:
```python
def _strip_category_prefix(text: str) -> str:
    # 대문자 단어(공백 포함 연속)를 앞에서 제거. e.g. "TECH BLOGApache..." → "Apache..."
    return re.sub(r'^(?:[A-Z]{2,}\s*)+', '', text).strip()
```

- [ ] **Step 2: `_fetch_article_text` 헬퍼 추가**

파일 상단 import 바로 아래에 추가:

```python
def _fetch_article_text(url: str, max_chars: int = 2000) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # script/style 제거
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        # <article> 또는 <main> 우선, 없으면 <body>
        container = soup.find("article") or soup.find("main") or soup.body
        if not container:
            return ""
        text = " ".join(container.get_text(" ", strip=True).split())
        return text[:max_chars]
    except Exception:
        return ""
```

- [ ] **Step 3: fetch_uber, fetch_alibaba, fetch_spotify에 content 필드 추가**

각 함수의 `items.append({...})` 부분에서 `"summary": ""` 대신:

```python
# fetch_uber 내부
items.append({
    "title": title,
    "url": href,
    "source": "Uber Engineering",
    "summary": "",
    "content": _fetch_article_text(href),
})

# fetch_alibaba 내부
items.append({
    "title": title,
    "url": href,
    "source": "Alibaba Cloud Blog",
    "summary": "",
    "content": _fetch_article_text(href),
})

# fetch_spotify 내부
items.append({
    "title": title,
    "url": full_url,
    "source": "Spotify Engineering",
    "summary": "",
    "content": _fetch_article_text(full_url),
})
```

- [ ] **Step 4: 확인**

```bash
cd /Users/kimeunmi/source/project/trending-tech
.venv/bin/python -c "
from sources.scraper import fetch_uber
items = fetch_uber(max_items=1)
print('title:', items[0]['title'])
print('content len:', len(items[0].get('content','')))
print('content[:100]:', items[0].get('content','')[:100])
"
```
Expected: `content len` > 300

---

### Task 3: `main.py` — 번역·요약 파이프라인 업데이트

**Files:**
- Modify: `main.py`

- [ ] **Step 1: `_add_summaries` 함수 업데이트 — content 필드 활용 + 제목 번역**

현재:
```python
def _add_summaries(items: list[dict], content_key: str) -> list[dict]:
    for item in items:
        content = item.get(content_key) or item.get("description") or item.get("abstract") or ""
        item["summary"] = summarize_item(item.get("title") or item.get("name", ""), content)
    return items
```

수정:
```python
from summarizer import summarize_item, filter_important_papers, generate_highlights, translate_title

def _add_summaries(items: list[dict], content_key: str) -> list[dict]:
    for item in items:
        content = (item.get(content_key) or item.get("content") or
                   item.get("description") or item.get("abstract") or "")
        title = item.get("title") or item.get("name", "")
        item["summary"] = summarize_item(title, content)
        item["title_ko"] = translate_title(title)
    return items
```

- [ ] **Step 2: github 항목도 번역 — `summarize` 함수 내**

현재 github summarize 호출:
```python
data["github"] = _add_summaries(data["github"], "description")
```

`_add_summaries` 수정으로 자동 적용됨. 별도 변경 불필요.

- [ ] **Step 3: 확인 — import 오류 없는지 체크**

```bash
cd /Users/kimeunmi/source/project/trending-tech
.venv/bin/python -c "from main import _add_summaries; print('ok')"
```
Expected: `ok`

---

### Task 4: `renderer.py` — 한국어 제목 우선 표시

**Files:**
- Modify: `renderer.py`

- [ ] **Step 1: `_item_html` 함수 업데이트**

현재:
```python
def _item_html(name: str, url: str, meta: str, summary: str) -> str:
    return f"""<div class="item">
  <div class="item-left">
    <div class="item-name"><a href="{url}" target="_blank" rel="noopener">{_e(name)}</a></div>
    <div class="item-meta">{_e(meta)}</div>
    <div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>
  </div>
  <div class="item-arrow"><a href="{url}" target="_blank" rel="noopener">&rarr;</a></div>
</div>"""
```

수정 (name_ko 파라미터 추가):
```python
def _item_html(name: str, url: str, meta: str, summary: str, name_ko: str = "") -> str:
    display_name = name_ko if name_ko and name_ko.strip() else name
    return f"""<div class="item">
  <div class="item-left">
    <div class="item-name"><a href="{url}" target="_blank" rel="noopener">{_e(display_name)}</a></div>
    <div class="item-meta">{_e(meta)}</div>
    <div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>
  </div>
  <div class="item-arrow"><a href="{url}" target="_blank" rel="noopener">&rarr;</a></div>
</div>"""
```

- [ ] **Step 2: `render_daily_page` 내 `_item_html` 호출부 업데이트**

company_blogs, dev_blogs, papers, hn_reddit, github 섹션 각각에서 `name_ko=i.get("title_ko","")` 추가:

```python
# company_blogs
_item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""), i.get("title_ko",""))

# dev_blogs
_item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""), i.get("title_ko",""))

# papers
_item_html(i["title"], i["url"], "arXiv", i.get("summary", i.get("abstract","")), i.get("title_ko",""))

# hn_reddit
_item_html(
    i.get("title",""), i["url"],
    f"{i.get('source','HN')} · {i.get('points',0)} pts" if "points" in i else i.get("source",""),
    i.get("summary",""), i.get("title_ko",""))

# github — name은 한국어 번역 불필요(repo명), description 표시
_item_html(i["name"], i["url"], i.get("stars_today",""), i.get("summary", i.get("description","")))
```

- [ ] **Step 3: 확인 — import 오류 없는지 체크**

```bash
cd /Users/kimeunmi/source/project/trending-tech
.venv/bin/python -c "from renderer import render_daily_page; print('ok')"
```
Expected: `ok`

---

### Task 5: 2026-05-31 재생성 스크립트 작성 + 실행

**Files:**
- Create: `rerender.py` (임시 스크립트)

- [ ] **Step 1: rerender.py 작성**

```python
#!/usr/bin/env python3
"""특정 날짜 HTML 재생성 (수집 → 요약 → HTML 저장)"""
import sys
from main import collect, summarize, save_html

def rerender(date_str: str):
    print(f"[rerender] {date_str} 재생성 시작")
    data = collect(date_str)
    data = summarize(data)
    save_html(data)
    print(f"[rerender] 완료: docs/{date_str}.html")

if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-05-31"
    rerender(date_str)
```

- [ ] **Step 2: 실행**

```bash
cd /Users/kimeunmi/source/project/trending-tech
.venv/bin/python rerender.py 2026-05-31
```
Expected: `[rerender] 완료: docs/2026-05-31.html`

- [ ] **Step 3: 결과 확인**

```bash
grep -c 'item-summary"></div>' /Users/kimeunmi/source/project/trending-tech/docs/2026-05-31.html
```
Expected: 0 또는 대폭 감소 (빈 요약 없어야 함)

```bash
grep 'item-name' /Users/kimeunmi/source/project/trending-tech/docs/2026-05-31.html | head -5
```
Expected: 한국어 제목이 포함된 라인들

---

## 수정 완료 후 git commit

```bash
cd /Users/kimeunmi/source/project/trending-tech
git add summarizer.py sources/scraper.py main.py renderer.py docs/2026-05-31.html docs/2026-05-31.json
git commit -m "feat: 한국어 제목 번역, 기사 본문 수집으로 요약 생성"
git push
```
