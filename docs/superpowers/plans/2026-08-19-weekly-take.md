# 주간 해석 + 주요 문서 선별 Implementation Plan

**Goal:** 주간 페이지에 "이 주의 해석" 한 문장과, 그 주 일별 ★ 글들 중 다시 골라낸 핵심 문서
5건 미만을 링크와 함께 싣는다.

**Architecture:** 일별 JSON 에 해석(`today_take`)과 ★ 글(`important_links`)을 저장한다.
주간 페이지를 만들 때 그 주의 일별 JSON 을 모아 LLM 호출 1회로 주간 해석과 상위 문서를 뽑는다.
기존 페이지에는 이 필드가 없으므로 HTML 에서 파싱하는 폴백을 둔다.

## 변경 파일

| 파일 | 변경 |
|---|---|
| `main.py` | `save_html` 이 today_take·important_links 저장 / `save_weekly_page` 가 주간 해석 생성 |
| `summarizer.py` | `generate_week_take(days)` 추가 |
| `renderer.py` | 주간 페이지에 해석 섹션 + 문서 링크 목록 |
| `weekly.py` (신규) | 일별 데이터 로더 (JSON 우선, HTML 폴백) |

## 결정사항

- **주간 해석은 매일 갱신한다.** 주간 페이지가 매일 다시 그려지므로 최신 상태를 유지한다.
  LLM 호출 1회 추가.
- **선별 개수는 4건.** "5개 미만" 요구에 맞춘다.
- **과거 페이지는 HTML 파싱으로 소급한다.** `take-headline`, `item important` 를 읽는다.
  JSON 에 필드가 있으면 그쪽을 우선한다.
- 주간 해석 생성이 실패하면 섹션을 그리지 않는다. 주간 페이지 나머지는 그대로 나온다.

## Task 1: 일별 데이터 로더 (weekly.py)

- `load_day(date_str) -> dict` : `{"date","headline","body","links":[{"text","url"}]}`
- JSON 에 `today_take` 가 있으면 사용, 없으면 `docs/{date}.html` 에서 파싱
- 파일이 없거나 파싱 실패하면 빈 dict

## Task 2: 저장 (main.save_html)

일별 JSON 에 추가:
```json
{"today_take": {"headline": "...", "body": "..."},
 "important_links": [{"text": "...", "url": "..."}]}
```

## Task 3: 주간 해석 (summarizer.generate_week_take)

입력: 일별 `{날짜, headline, links[]}` 목록
출력: `{"headline", "body", "picks": [{"text","url","why"}]}` (picks 4건)

프롬프트 요지:
- 하루짜리 해석들을 나열하지 말고 **일주일을 관통하는 흐름 하나**를 짚는다
- picks 는 그 주 전체에서 가장 중요한 문서 4건. 왜 중요한지 한 줄(`why`)을 붙인다
- 목록에 없는 것을 지어내지 않는다

## Task 4: 렌더링

주간 페이지 상단에 "이 주의 해석" 섹션:
- headline (큰 글씨) + body
- 그 아래 핵심 문서 4건: 제목 링크 + why 한 줄
