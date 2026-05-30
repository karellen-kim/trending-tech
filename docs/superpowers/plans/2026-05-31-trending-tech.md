# Trending Tech Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 23:55 cron으로 GitHub Trending·HN·arXiv·개발자 블로그를 수집, claude CLI로 요약해 정적 HTML을 생성하고 git push + Slack 전송.

**Architecture:** Python 스크립트가 소스별 수집기를 ThreadPoolExecutor로 병렬 실행, `claude -p` subprocess로 요약, renderer.py가 HTML 생성, notifier.py가 Slack Webhook POST. cron으로 23:55 자동 실행.

**Tech Stack:** Python 3.10+, requests, beautifulsoup4, feedparser, python-dotenv, pytest

---

### Task 1: 프로젝트 초기 설정

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.py`
- Create: `sources/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: requirements.txt 생성**

```
requests==2.32.3
beautifulsoup4==4.12.3
feedparser==6.0.11
python-dotenv==1.0.1
pytest==8.3.4
```

- [ ] **Step 2: .gitignore 생성**

```
.env
__pycache__/
*.pyc
.venv/
logs/*.log
```

- [ ] **Step 3: .env.example 생성**

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
```

- [ ] **Step 4: config.py 생성**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

MAX_GITHUB_ITEMS = 10
MAX_HN_ITEMS = 10
MAX_PAPER_ITEMS = 5
MAX_BLOG_ITEMS = 5

RSS_SOURCES = [
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed"},
    {"name": "Andrej Karpathy", "url": "https://karpathy.github.io/feed.xml"},
    {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/"},
]

ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",
    "https://rss.arxiv.org/rss/cs.LG",
    "https://rss.arxiv.org/rss/cs.CL",
]
```

- [ ] **Step 5: 디렉토리 및 빈 파일 생성**

```bash
mkdir -p sources tests logs docs
touch sources/__init__.py tests/__init__.py logs/.gitkeep
```

- [ ] **Step 6: 가상환경 및 패키지 설치**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 7: 커밋**

```bash
git init
git add requirements.txt .gitignore .env.example config.py sources/__init__.py tests/__init__.py logs/.gitkeep
git commit -m "chore: project scaffold"
```

---

### Task 2: GitHub Trending 수집기

**Files:**
- Create: `sources/github.py`
- Create: `tests/test_github.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_github.py
from unittest.mock import patch, MagicMock
from sources.github import fetch_trending

MOCK_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/microsoft/phi-4">microsoft / <strong>phi-4</strong></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A small language model</p>
  <span class="float-sm-right">
    <a href="/microsoft/phi-4/stargazers">1,234 stars today</a>
  </span>
</article>
"""

def test_fetch_trending_returns_list():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_HTML
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.github.requests.get", return_value=mock_resp):
        items = fetch_trending()
    assert isinstance(items, list)

def test_fetch_trending_parses_repo():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_HTML
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.github.requests.get", return_value=mock_resp):
        items = fetch_trending()
    assert len(items) == 1
    assert items[0]["name"] == "microsoft/phi-4"
    assert items[0]["url"] == "https://github.com/microsoft/phi-4"
    assert "small language model" in items[0]["description"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_github.py -v
```
Expected: FAIL (ImportError)

- [ ] **Step 3: sources/github.py 구현**

```python
import requests
from bs4 import BeautifulSoup
from config import MAX_GITHUB_ITEMS

TRENDING_URL = "https://github.com/trending"

def fetch_trending(since: str = "daily") -> list[dict]:
    resp = requests.get(TRENDING_URL, params={"since": since}, timeout=15,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for article in soup.select("article.Box-row")[:MAX_GITHUB_ITEMS]:
        a = article.select_one("h2 a")
        if not a:
            continue
        path = a["href"].strip("/")
        desc_el = article.select_one("p.col-9")
        stars_el = article.select_one("a[href$='/stargazers']")
        items.append({
            "name": path,
            "url": f"https://github.com/{path}",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "stars_today": stars_el.get_text(strip=True) if stars_el else "",
        })
    return items
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_github.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sources/github.py tests/test_github.py
git commit -m "feat: github trending collector"
```

---

### Task 3: Hacker News 수집기

**Files:**
- Create: `sources/hackernews.py`
- Create: `tests/test_hackernews.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_hackernews.py
from unittest.mock import patch, MagicMock
from sources.hackernews import fetch_top_stories

MOCK_RESPONSE = {
    "hits": [{
        "objectID": "123",
        "title": "LLaMA 4 Released",
        "url": "https://example.com/llama4",
        "points": 500,
        "num_comments": 200,
    }]
}

def test_fetch_top_stories_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.hackernews.requests.get", return_value=mock_resp):
        items = fetch_top_stories()
    assert isinstance(items, list)

def test_fetch_top_stories_parses_item():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    with patch("sources.hackernews.requests.get", return_value=mock_resp):
        items = fetch_top_stories()
    assert items[0]["title"] == "LLaMA 4 Released"
    assert items[0]["url"] == "https://example.com/llama4"
    assert items[0]["points"] == 500
    assert items[0]["comments"] == 200
    assert items[0]["hn_url"] == "https://news.ycombinator.com/item?id=123"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_hackernews.py -v
```
Expected: FAIL

- [ ] **Step 3: sources/hackernews.py 구현**

```python
import requests
from config import MAX_HN_ITEMS

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

def fetch_top_stories() -> list[dict]:
    resp = requests.get(ALGOLIA_URL, params={"tags": "front_page", "hitsPerPage": MAX_HN_ITEMS}, timeout=15)
    resp.raise_for_status()
    items = []
    for hit in resp.json().get("hits", [])[:MAX_HN_ITEMS]:
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append({
            "title": hit.get("title", ""),
            "url": url,
            "points": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "hn_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
        })
    return items
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_hackernews.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sources/hackernews.py tests/test_hackernews.py
git commit -m "feat: hacker news collector"
```

---

### Task 4: RSS 블로그 수집기

**Files:**
- Create: `sources/rss.py`
- Create: `tests/test_rss.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_rss.py
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
    with patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert isinstance(items, list)

def test_fetch_rss_entries_parses_entry():
    with patch("sources.rss.feedparser.parse", return_value=_mock_feed()):
        items = fetch_rss_entries("Test Blog", "https://example.com/feed")
    assert len(items) == 1
    assert items[0]["title"] == "New Post"
    assert items[0]["url"] == "https://example.com/post"
    assert items[0]["source"] == "Test Blog"
    assert "summary" in items[0]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_rss.py -v
```
Expected: FAIL

- [ ] **Step 3: sources/rss.py 구현**

```python
import feedparser
from datetime import datetime, timezone, timedelta
from config import RSS_SOURCES, MAX_BLOG_ITEMS

def fetch_rss_entries(name: str, url: str, max_items: int = MAX_BLOG_ITEMS) -> list[dict]:
    feed = feedparser.parse(url)
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    for entry in feed.entries:
        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue
        except Exception:
            pass
        summary = entry.get("summary", "") or ""
        items.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "source": name,
            "summary": summary[:500],
        })
        if len(items) >= max_items:
            break
    return items

def fetch_all_blogs() -> list[dict]:
    all_items = []
    for source in RSS_SOURCES:
        try:
            all_items.extend(fetch_rss_entries(source["name"], source["url"]))
        except Exception as e:
            print(f"[RSS] {source['name']} 실패: {e}")
    return all_items
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_rss.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sources/rss.py tests/test_rss.py
git commit -m "feat: rss blog collector"
```

---

### Task 5: arXiv 논문 수집기

**Files:**
- Create: `sources/arxiv.py`
- Create: `tests/test_arxiv.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_arxiv.py
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
    with patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert isinstance(items, list)

def test_fetch_arxiv_papers_parses_entry():
    with patch("sources.arxiv.feedparser.parse", return_value=_mock_feed()):
        items = fetch_arxiv_papers("https://rss.arxiv.org/rss/cs.AI")
    assert items[0]["title"] == "Attention Is All You Need 2.0"
    assert "arxiv.org" in items[0]["url"]
    assert "abstract" in items[0]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_arxiv.py -v
```
Expected: FAIL

- [ ] **Step 3: sources/arxiv.py 구현**

```python
import feedparser
from config import ARXIV_FEEDS

def fetch_arxiv_papers(feed_url: str) -> list[dict]:
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries:
        items.append({
            "title": entry.get("title", "").replace("\n", " ").strip(),
            "url": entry.get("link", ""),
            "abstract": entry.get("summary", "")[:600],
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

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_arxiv.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add sources/arxiv.py tests/test_arxiv.py
git commit -m "feat: arxiv paper collector"
```

---

### Task 6: Claude CLI 요약기

**Files:**
- Create: `summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_summarizer.py
from unittest.mock import patch, MagicMock
from summarizer import summarize_item, filter_important_papers

def _mock_proc(stdout="요약 결과입니다.", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m

def test_summarize_item_returns_string():
    with patch("summarizer.subprocess.run", return_value=_mock_proc()):
        result = summarize_item("phi-4", "A small but capable language model by Microsoft.")
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_summarizer.py -v
```
Expected: FAIL

- [ ] **Step 3: summarizer.py 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_summarizer.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add summarizer.py tests/test_summarizer.py
git commit -m "feat: claude cli summarizer"
```

---

### Task 7: HTML 렌더러

**Files:**
- Create: `renderer.py`
- Create: `tests/test_renderer.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_renderer.py
from renderer import render_daily_page, render_index_page

SAMPLE_DATA = {
    "date": "2026-05-31",
    "github": [{"name": "microsoft/phi-4", "url": "https://github.com/microsoft/phi-4",
                "description": "Small LM", "stars_today": "1,234 stars", "summary": "경량 모델입니다."}],
    "hn": [{"title": "LLaMA 4 Released", "url": "https://example.com",
            "points": 500, "comments": 200, "hn_url": "https://news.ycombinator.com/item?id=1",
            "summary": "오픈소스 LLM입니다."}],
    "papers": [{"title": "Paper A", "url": "https://arxiv.org/abs/1",
                "abstract": "...", "summary": "트랜스포머 개선입니다."}],
    "blogs": [{"title": "New Post", "url": "https://martinfowler.com/post",
               "source": "Martin Fowler", "summary": "패턴 글입니다."}],
}

def test_render_daily_page_is_html():
    html = render_daily_page(SAMPLE_DATA)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026-05-31" in html

def test_render_daily_page_has_sections():
    html = render_daily_page(SAMPLE_DATA)
    assert "GitHub Trending" in html
    assert "Hacker News" in html
    assert "AI / LLM Papers" in html
    assert "Developer Blogs" in html

def test_render_daily_page_has_items():
    html = render_daily_page(SAMPLE_DATA)
    assert "microsoft/phi-4" in html
    assert "LLaMA 4 Released" in html

def test_render_index_page_is_html():
    entries = [{"date": "2026-05-31", "highlights": ["LLaMA 4", "phi-4"]}]
    html = render_index_page(entries)
    assert html.startswith("<!DOCTYPE html>")
    assert "2026" in html
    assert "2026-05-31" in html
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_renderer.py -v
```
Expected: FAIL

- [ ] **Step 3: renderer.py 구현**

```python
# renderer.py
from collections import defaultdict

_FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">"""

_BASE_CSS = """<style>
  :root {
    --paper: oklch(1 0 0); --paper-deep: oklch(0.985 0 0);
    --ink: oklch(0.18 0.015 260); --ink-soft: oklch(0.38 0.012 260); --ink-faint: oklch(0.58 0.008 260);
    --rule: oklch(0.90 0.005 260); --accent: oklch(0.55 0.16 38);
    --accent-deep: oklch(0.40 0.14 38); --accent-wash: oklch(0.96 0.025 50);
    --sans: "IBM Plex Sans KR", -apple-system, sans-serif;
    --mono: "JetBrains Mono", ui-monospace, monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 15px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
</style>"""

_DAILY_CSS = """<style>
  body { max-width: 860px; margin: 0 auto; padding: 3rem 2rem; }
  .back-btn { display: inline-block; font-size: 0.78rem; font-weight: 500; color: var(--ink-soft); text-decoration: none; border: 1px solid var(--rule); padding: 0.3rem 0.7rem; margin-bottom: 3rem; }
  .back-btn:hover { border-color: var(--accent); color: var(--accent-deep); }
  .page-meta { font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.4rem; }
  h1 { font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1; margin-bottom: 3rem; }
  h1 em { font-style: normal; color: var(--accent); }
  .section { margin-bottom: 3rem; }
  .section-title { font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-faint); font-weight: 600; padding-bottom: 0.6rem; border-bottom: 2px solid var(--ink); }
  .item { display: grid; grid-template-columns: 1fr auto; gap: 1rem; padding: 1rem 0; border-bottom: 1px solid var(--rule); }
  .item:last-child { border-bottom: none; }
  .item-name { font-weight: 600; font-size: 0.98rem; margin-bottom: 0.2rem; }
  .item-name a { color: var(--ink); text-decoration: none; }
  .item-name a:hover { color: var(--accent-deep); }
  .item-meta { font-family: var(--mono); font-size: 0.65rem; color: var(--ink-faint); margin-bottom: 0.5rem; }
  .item-summary { font-size: 0.88rem; color: var(--ink-soft); line-height: 1.65; }
  .item-arrow { font-family: var(--mono); font-size: 0.85rem; color: var(--ink-faint); padding-top: 0.1rem; }
  .item-arrow a { color: inherit; text-decoration: none; }
  .item-arrow a:hover { color: var(--accent); }
</style>"""

_INDEX_CSS = """<style>
  body { display: flex; min-height: 100vh; }
  .sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--rule); position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 2rem 0; }
  .sidebar-header { padding: 0 1.4rem 1.4rem; border-bottom: 1px solid var(--rule); margin-bottom: 1rem; }
  .s-label { font-size: 0.62rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; margin-bottom: 0.4rem; }
  .s-title { font-size: 1rem; font-weight: 700; color: var(--ink); letter-spacing: -0.02em; }
  .year-btn { width: 100%; padding: 0.7rem 1.4rem; display: block; cursor: pointer; background: none; border: none; font-family: var(--sans); text-align: left; font-size: 0.9rem; font-weight: 500; color: var(--ink-soft); border-left: 2px solid transparent; transition: all 0.12s; }
  .year-btn:hover { background: var(--paper-deep); }
  .year-btn.active { background: var(--accent-wash); border-left-color: var(--accent); color: var(--accent-deep); font-weight: 600; }
  .main { flex: 1; padding: 3rem 4rem; max-width: 800px; }
  .main-label { font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.5rem; }
  h1 { font-size: 2.8rem; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 2.5rem; }
  h1 em { font-style: normal; color: var(--accent); }
  .year-section { display: none; }
  .month-block { margin-bottom: 0.5rem; }
  .month-btn { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 0.8rem 0; background: none; border: none; border-bottom: 1px solid var(--rule); cursor: pointer; font-family: var(--sans); }
  .month-btn:hover .month-label { color: var(--accent-deep); }
  .month-label { font-size: 0.95rem; font-weight: 600; color: var(--ink); }
  .month-arrow { font-family: var(--mono); font-size: 0.8rem; color: var(--ink-faint); transition: transform 0.2s; }
  .month-btn.open .month-arrow { transform: rotate(90deg); color: var(--accent); }
  .month-highlights { padding: 0.6rem 0 0.4rem 0.5rem; }
  .month-highlights ul { list-style: none; padding: 0; }
  .month-highlights li { font-size: 0.85rem; color: var(--ink-soft); padding: 0.2rem 0 0.2rem 1rem; position: relative; }
  .month-highlights li::before { content: "·"; position: absolute; left: 0; color: var(--accent); }
  .month-dates { padding: 0.6rem 0; display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .date-link { font-family: var(--mono); font-size: 0.75rem; padding: 0.25rem 0.6rem; border: 1px solid var(--rule); color: var(--ink-soft); text-decoration: none; transition: all 0.12s; }
  .date-link:hover { border-color: var(--accent); color: var(--accent-deep); background: var(--accent-wash); }
</style>"""

_MONTH_NAMES = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
                "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"}

def _e(s: str) -> str:
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _item_html(name: str, url: str, meta: str, summary: str) -> str:
    return f"""<div class="item">
  <div class="item-left">
    <div class="item-name"><a href="{url}" target="_blank" rel="noopener">{_e(name)}</a></div>
    <div class="item-meta">{_e(meta)}</div>
    <div class="item-summary">{_e(summary).replace(chr(10), "<br>")}</div>
  </div>
  <div class="item-arrow"><a href="{url}" target="_blank" rel="noopener">→</a></div>
</div>"""

def _section_html(title: str, items_html: str) -> str:
    return f"""<div class="section">
  <div class="section-title">{title}</div>
  {items_html}
</div>"""

def render_daily_page(data: dict) -> str:
    date = data["date"]
    y, m, d = date.split("-")

    sections = ""
    if data.get("github"):
        sections += _section_html("GitHub Trending", "".join(
            _item_html(i["name"], i["url"], i.get("stars_today",""), i.get("summary", i.get("description","")))
            for i in data["github"]))
    if data.get("hn"):
        sections += _section_html("Hacker News", "".join(
            _item_html(i["title"], i["url"], f"{i.get('points',0)} pts · {i.get('comments',0)} comments", i.get("summary",""))
            for i in data["hn"]))
    if data.get("papers"):
        sections += _section_html("AI / LLM Papers", "".join(
            _item_html(i["title"], i["url"], "arXiv", i.get("summary", i.get("abstract","")))
            for i in data["papers"]))
    if data.get("blogs"):
        sections += _section_html("Developer Blogs", "".join(
            _item_html(i["title"], i["url"], i.get("source",""), i.get("summary",""))
            for i in data["blogs"]))

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{date} — Trending Tech</title>
{_FONTS}
{_BASE_CSS}
{_DAILY_CSS}
</head>
<body>
<a href="./index.html" class="back-btn">← index</a>
<div class="page-meta">TRENDING-TECH · {date}</div>
<h1><em>{d}</em> {_MONTH_NAMES[m]} {y}</h1>
{sections}
</body>
</html>"""

def render_index_page(entries: list[dict]) -> str:
    by_year = defaultdict(lambda: defaultdict(list))
    for e in sorted(entries, key=lambda x: x["date"], reverse=True):
        y, m, _ = e["date"].split("-")
        by_year[y][m].append(e)

    years = sorted(by_year.keys(), reverse=True)
    sidebar = "".join(
        f'<button class="year-btn" data-year="{y}" onclick="showYear(\'{y}\')">{y}</button>'
        for y in years)

    year_sections = ""
    for y in years:
        months_html = ""
        for m in sorted(by_year[y].keys(), reverse=True):
            entries_in_month = by_year[y][m]
            highlights = []
            for e in entries_in_month:
                highlights.extend(e.get("highlights", [])[:2])
            hl_html = "".join(f"<li>{_e(h)}</li>" for h in highlights[:3])
            dates_html = "".join(
                f'<a href="./{e["date"]}.html" class="date-link">{e["date"]}</a>'
                for e in sorted(entries_in_month, key=lambda x: x["date"], reverse=True))
            months_html += f"""<div class="month-block">
  <button class="month-btn" onclick="toggleMonth(this)">
    <span class="month-label">{y}.{m} {_MONTH_NAMES[m]}</span>
    <span class="month-arrow">→</span>
  </button>
  <div class="month-highlights"><ul>{hl_html}</ul></div>
  <div class="month-dates" style="display:none">{dates_html}</div>
</div>"""
        year_sections += f'<div class="year-section" id="year-{y}">{months_html}</div>'

    first_year = years[0] if years else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trending Tech</title>
{_FONTS}
{_BASE_CSS}
{_INDEX_CSS}
</head>
<body>
<nav class="sidebar">
  <div class="sidebar-header">
    <div class="s-label">trending</div>
    <div class="s-title">tech</div>
  </div>
  {sidebar}
</nav>
<main class="main">
  <div class="main-label">TRENDING-TECH · ARCHIVE</div>
  <h1>all <em>trends</em></h1>
  {year_sections}
</main>
<script>
function showYear(y) {{
  document.querySelectorAll('.year-section').forEach(s => s.style.display = 'none');
  document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('year-' + y).style.display = 'block';
  document.querySelector('[data-year="' + y + '"]').classList.add('active');
}}
function toggleMonth(btn) {{
  btn.classList.toggle('open');
  const dates = btn.nextElementSibling.nextElementSibling;
  dates.style.display = dates.style.display === 'none' ? 'flex' : 'none';
}}
if ('{first_year}') showYear('{first_year}');
</script>
</body>
</html>"""
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_renderer.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add renderer.py tests/test_renderer.py
git commit -m "feat: html renderer daily + index"
```

---

### Task 8: Slack 알림

**Files:**
- Create: `notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_notifier.py
from unittest.mock import patch, MagicMock
from notifier import send_slack

def test_send_slack_posts_to_webhook():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("notifier.requests.post", return_value=mock_resp) as mock_post:
        send_slack("https://hooks.slack.com/test", "2026-05-31", ["LLaMA 4", "phi-4"])
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "2026-05-31" in payload["text"]

def test_send_slack_skips_empty_url():
    with patch("notifier.requests.post") as mock_post:
        send_slack("", "2026-05-31", ["item1"])
    mock_post.assert_not_called()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_notifier.py -v
```
Expected: FAIL

- [ ] **Step 3: notifier.py 구현**

```python
import requests

def send_slack(webhook_url: str, date: str, highlights: list[str]) -> None:
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL 미설정, 전송 건너뜀")
        return
    hl_text = "\n".join(f"• {h}" for h in highlights[:5])
    text = f"*{date} 개발 트렌드*\n{hl_text}\nhttps://github.com/karellen-kim/trending-tech/blob/main/docs/{date}.html"
    resp = requests.post(webhook_url, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"[Slack] 전송 실패: {resp.status_code} {resp.text}")
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_notifier.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: slack notifier"
```

---

### Task 9: 메인 오케스트레이터

**Files:**
- Create: `main.py`

- [ ] **Step 1: main.py 구현**

```python
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from config import DOCS_DIR, LOGS_DIR, SLACK_WEBHOOK_URL, MAX_PAPER_ITEMS
from sources.github import fetch_trending
from sources.hackernews import fetch_top_stories
from sources.rss import fetch_all_blogs
from sources.arxiv import fetch_all_papers
from summarizer import summarize_item, filter_important_papers
from renderer import render_daily_page, render_index_page
from notifier import send_slack


def _add_summaries(items: list[dict], content_key: str) -> list[dict]:
    for item in items:
        content = item.get(content_key) or item.get("description") or item.get("abstract") or ""
        item["summary"] = summarize_item(item.get("title") or item.get("name", ""), content)
    return items


def collect(today: str) -> dict:
    print(f"[{today}] 수집 시작")
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_gh = ex.submit(fetch_trending)
        f_hn = ex.submit(fetch_top_stories)
        f_bl = ex.submit(fetch_all_blogs)
        f_ar = ex.submit(fetch_all_papers)
        github, hn, blogs, papers = f_gh.result(), f_hn.result(), f_bl.result(), f_ar.result()
    print(f"  GitHub:{len(github)} HN:{len(hn)} Blogs:{len(blogs)} Papers:{len(papers)}")
    papers = filter_important_papers(papers, max_items=MAX_PAPER_ITEMS)
    return {"date": today, "github": github, "hn": hn, "blogs": blogs, "papers": papers}


def summarize(data: dict) -> dict:
    print("[요약] 시작")
    data["github"] = _add_summaries(data["github"], "description")
    data["hn"] = _add_summaries(data["hn"], "title")
    data["papers"] = _add_summaries(data["papers"], "abstract")
    data["blogs"] = _add_summaries(data["blogs"], "summary")
    return data


def save_html(data: dict) -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    today = data["date"]

    (DOCS_DIR / f"{today}.html").write_text(render_daily_page(data), encoding="utf-8")
    print(f"[HTML] docs/{today}.html 저장")

    highlights = (
        [i.get("name", "") for i in data["github"][:2]] +
        [i.get("title", "") for i in data["hn"][:2]]
    )
    (DOCS_DIR / f"{today}.json").write_text(
        json.dumps({"date": today, "highlights": highlights}, ensure_ascii=False),
        encoding="utf-8"
    )

    entries = []
    for jf in sorted(DOCS_DIR.glob("????-??-??.json")):
        try:
            entries.append(json.loads(jf.read_text(encoding="utf-8")))
        except Exception:
            pass
    (DOCS_DIR / "index.html").write_text(render_index_page(entries), encoding="utf-8")
    print("[HTML] docs/index.html 업데이트")
    return highlights


def git_commit_push(date_str: str) -> None:
    subprocess.run(["git", "add", f"docs/{date_str}.html", f"docs/{date_str}.json", "docs/index.html"], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: {date_str} trends"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("[Git] 커밋 + 푸시 완료")


def main():
    today = str(date.today())
    data = collect(today)
    data = summarize(data)
    highlights = save_html(data)
    git_commit_push(today)
    send_slack(SLACK_WEBHOOK_URL, today, highlights)
    print(f"[완료] {today}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 커밋**

```bash
git add main.py
git commit -m "feat: main orchestrator"
```

---

### Task 10: GitHub 리포지토리 생성 + cron 등록

**Files:** 없음 (설정 작업)

- [ ] **Step 1: GitHub 리포지토리 생성**

```bash
cd /Users/kimeunmi/source/project/trending-tech
git branch -M main
gh repo create trending-tech --public --source=. --remote=origin --push
```

- [ ] **Step 2: .env 파일 생성**

```bash
cp .env.example .env
# .env 열어서 SLACK_WEBHOOK_URL= 에 실제 Webhook URL 입력
```

- [ ] **Step 3: cron 등록**

```bash
crontab -e
```

다음 줄 추가:
```
55 23 * * * cd /Users/kimeunmi/source/project/trending-tech && /Users/kimeunmi/source/project/trending-tech/.venv/bin/python main.py >> /Users/kimeunmi/source/project/trending-tech/logs/cron.log 2>&1
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
pytest -v
```
Expected: 모든 테스트 PASS

- [ ] **Step 5: 수동 실행 확인**

```bash
source .venv/bin/activate
python main.py
```
Expected: `docs/YYYY-MM-DD.html`, `docs/index.html` 생성, git push, Slack 전송
