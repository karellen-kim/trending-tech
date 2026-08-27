# launchd 환경 claude CLI 인증 실패 수정 Plan

**작성일:** 2026-08-03

## 문제

`https://karellen-kim.github.io/trending-tech/2026-08-02.html` 의 28개 항목 전부
`<div class="item-summary"></div>` (빈 요약). 제목도 전부 영어(번역 실패).
`docs/2026-08-02.json` 의 highlights 도 LLM 생성물이 아닌 fallback
(`main.py:97-99` 의 github name 2개 + hn title 2개).

## 근본 원인 (실측으로 확정)

`summarizer._run_claude()` 가 `claude -p` 를 subprocess 로 호출하는데,
launchd 환경에서 인증에 실패해 returncode 1 → 빈 문자열 반환.
요약·번역·하이라이트가 모두 같은 함수를 타므로 전멸.

단일 변수 이분 탐색 결과, **`USER` 환경변수가 없으면 claude CLI 가 Keychain 의
OAuth 자격증명을 읽지 못한다.** (토큰 자체는 유효한데 "OAuth session expired" 로 오인 표시)

```
env -i HOME=... PATH=... USER=kimeunmi  claude -p ... → exit 0
env -i HOME=... PATH=... TMPDIR=...     claude -p ... → exit 1 (Failed to authenticate)
env -i HOME=... PATH=... LANG=...       claude -p ... → exit 1
env -i HOME=... PATH=... SHELL=...      claude -p ... → exit 1
env -i HOME=... PATH=... LOGNAME=...    claude -p ... → exit 1
```

`~/Library/LaunchAgents/com.karellen.trending-tech.plist` 의 `EnvironmentVariables`
에는 `PATH` 와 `HOME` 만 있고 `USER` 가 없다.

## 변경 파일

1. `~/Library/LaunchAgents/com.karellen.trending-tech.plist`
   — `EnvironmentVariables` 에 `USER=kimeunmi` 추가. 파일 수정만으로는 반영되지 않으므로
   `launchctl bootout` → `bootstrap` 으로 재등록하고 로드된 job 의 env 를 확인한다.

2. `summarizer.py` `_run_claude()`
   — returncode != 0 일 때 stderr 를 stdout 으로 출력. 이번 장애가 하루 동안
   조용히 진행된 이유가 실패를 빈 문자열로 삼켰기 때문이다.

3. `renderer.py:225`
   — `i.get("summary", i.get("description",""))` 는 `summary` 키가 `""` 로 존재하면
   기본값이 쓰이지 않아 fallback 이 동작하지 않는다. `or` 로 변경.

## 검증 방법

일반 셸에서 실행하면 `USER` 가 이미 있어 무조건 성공하므로 판별력이 없다.
반드시 launchd 가 선언하는 env 를 그대로 재현해 실행한다:

```bash
env -i HOME=/Users/kimeunmi \
  PATH=/Users/kimeunmi/.local/bin:/usr/local/bin:/usr/bin:/bin \
  USER=kimeunmi \
  .venv/bin/python rerender.py 2026-08-02
```

성공 기준: 빈 `item-summary` 개수가 0 이 아니라 **감소**하는 것.
`_add_summaries` 는 HN 에 `content_key="title"`, Reddit 도 title 만 넘기고
`summarize_item` 은 150자 미만이면 `""` 를 반환하므로, HN(10)·Reddit·GitHub 항목은
구조상 요약이 생성되지 않는다. 기업/개발자 블로그 항목에서 요약이 생기면 수정 성공.

## 범위 밖 (이번에 건드리지 않음)

- HN/Reddit 항목에 요약이 없는 설계 문제 (본문을 수집하지 않음)
- 미커밋 `sources/scraper.py` / `config.py` 변경 (Uber 수집 로직)
- `collect()` 가 날짜 인자를 무시하고 항상 현재 데이터를 가져오는 문제
- `git push` — CLAUDE.md 규칙상 명시 요청 없이는 하지 않는다
