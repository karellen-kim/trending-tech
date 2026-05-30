# Trending Tech — Design Spec
Date: 2026-05-31

## Overview

매일 23:55 cron으로 개발 트렌드를 수집·요약해 HTML로 저장하고 git push + Slack 전송하는 자동화 시스템.

## Sources

| 소스 | 방법 | 제한 |
|------|------|------|
| GitHub Trending | BeautifulSoup HTML 스크래핑 | 10개 |
| Hacker News | Algolia API (JSON) | 10개 |
| arXiv cs.AI/LG/CL | RSS + Claude 중요도 필터 | 5개 |
| 개발자 블로그 RSS | feedparser | 5개 |

RSS 소스: Martin Fowler, Simon Willison, Lilian Weng, Sebastian Raschka, Andrej Karpathy, The Batch (Andrew Ng)

## Architecture

```
main.py (진입점)
  ├── sources/github.py
  ├── sources/hackernews.py
  ├── sources/rss.py
  ├── sources/arxiv.py
  ├── summarizer.py        claude -p subprocess
  ├── renderer.py          HTML 생성
  ├── notifier.py          Slack Webhook
  └── config.py
```

## Data Flow

1. 소스 수집 병렬 실행 (ThreadPoolExecutor)
2. 항목별 `claude -p "..."` 요약 (3~5줄)
3. `docs/YYYY-MM-DD.html` 생성
4. `docs/index.html` 업데이트
5. `git commit + push` (public repo: trending-tech)
6. Slack `#trending-tech` 전송

## HTML Output

**`docs/YYYY-MM-DD.html`**: 날짜별 요약. 섹션: GitHub Trending / Hacker News / AI Papers / Dev Blogs. karellen-kim 스타일 (IBM Plex Sans KR, oklch 컬러).

**`docs/index.html`**: 좌측 사이드바에 연도 목록. 연도 클릭 → 월별 하이라이트. 월 클릭 → 해당 월 날짜 목록. 날짜 클릭 → YYYY-MM-DD.html.

## Configuration

- `config.py`: 소스 URL, 항목 수 제한
- `.env`: `SLACK_WEBHOOK_URL` (gitignore)

## Cron

```
55 23 * * * cd /path/to/trending-tech && python main.py >> logs/cron.log 2>&1
```
