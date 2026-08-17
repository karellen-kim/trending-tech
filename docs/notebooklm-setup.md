# Gemini Notebook 오디오 오버뷰 설정

매일 하이라이트 5건의 원문 링크를 Gemini Notebook 에 올리고 AI 오디오 오버뷰 생성을 시킨다.
**오디오 파일은 내려받지 않는다** — 재생은 Gemini Notebook 에서 한다.
생성에 성공하면 일별 페이지 하이라이트 섹션에 노트북 링크가 붙는다.

**기본은 꺼져 있다.** 아래 준비를 마치고 `.env` 에 `ENABLE_NOTEBOOKLM=1` 을 넣어야 동작한다.

## 왜 브라우저 자동화인가

소비자용 Gemini Notebook 에는 공개 API 가 없다. 공식 API 는
[Gemini Notebook Enterprise](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-audio-overview)
에만 있고 Gemini Enterprise 라이선스가 필요하며 아직 Preview(`v1alpha`) 다.

커뮤니티 도구(`notebooklm-podcast-automator`)도 검토했으나 쓰지 않았다.
**2026-08 기준 제품이 바뀌었기 때문이다:**

```
notebooklm.google.com  →  notebook.google.com   (도메인 변경)
"NotebookLM"           →  "Gemini Notebook"     (제품명 변경)
```

그 도구는 옛 도메인과 영어·히브리어 UI 텍스트를 기준으로 셀렉터를 잡는다.
한국어 UI 에서는 동작하지 않고, 별도 FastAPI 서버를 상시 띄워야 한다.
필요한 동작이 "링크 올리고 생성 누르기" 뿐이라 직접 구현했다(`notebooklm.py`, 약 150줄).

## 준비 (최초 1회)

### 1. 의존성

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
```

### 2. 로그인 (사람이 직접)

```bash
.venv/bin/python -m notebooklm login
```

Chrome 창이 열린다. Google 로그인을 마치고 터미널에서 Enter 를 누르면
세션이 `~/.gemini-notebook-profile` 에 저장된다. 이후로는 자동으로 이 세션을 쓴다.

### 3. `.env` 설정

```
ENABLE_NOTEBOOKLM=1
```

노트북은 **매일 새로 만든다.** 제목은 `[Daily] YY.MM.DD 그날의 해석` 으로 붙는다.

선택 설정:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NOTEBOOKLM_FORMAT` | `deep_dive` | `deep_dive`(심층 분석) / `summary`(요약) / `criticism`(비평) / `debate`(토론) |
| `NOTEBOOKLM_LANGUAGE` | `ko` | 오디오 언어 |
| `NOTEBOOKLM_PROFILE_DIR` | `~/.gemini-notebook-profile` | 로그인 세션 저장 위치 |
| `NOTEBOOKLM_HEADLESS` | `1` | `0` 이면 창을 띄운다 (문제 진단용) |
| `NOTEBOOKLM_TIMEOUT` | `120` | 페이지 로드 대기(초) |

### 4. 실행

```bash
.venv/bin/python main.py
```

## 동작 순서

실제 화면에서 확인한 흐름이다.

```
오늘의 해석 생성 (headline + 근거 5건)
  → 노트북 새로 만들기
  → "웹사이트" 클릭 (빈 노트북은 소스 다이얼로그가 이미 열려 있다)
  → URL 5건을 줄바꿈으로 구분해 한 번에 입력       ← 화면이 이 방식을 안내한다
  → "삽입" 클릭
  → 소스 크롤링 대기
  → "AI 오디오 오버뷰" 클릭
  → 형식 선택 + 집중할 내용 프롬프트 입력
  → "생성" 클릭 → "AI 오디오 오버뷰 생성 중..." 확인
  → 노트북 제목을 "[Daily] YY.MM.DD 해석" 으로 설정 (마지막에 해야 한다)
  → 노트북 주소를 돌려주면 일별 페이지에 링크로 건다
```

**제목을 마지막에 설정하는 이유**: 소스를 넣으면 Gemini 가 내용을 보고 제목을 자동 생성해
덮어쓴다. 실측으로 `[Daily] 26.08.17 ...` 가 `Cloudflare and AWS AgentCore Monitoring ...` 로
바뀌는 것을 확인했다. 그래서 모든 작업이 끝난 뒤 설정하고, 값을 읽어 반영 여부를 확인한다.

## 알아둘 것

- **실패는 배치를 멈추지 않는다.** 로그인이 풀렸거나 UI 가 바뀌어도
  HTML 생성·커밋·푸시는 정상으로 끝나고 그날 페이지에 노트북 링크만 안 붙는다.
- **세션이 만료되면 사람이 다시 로그인해야 한다.** launchd 무인 실행 중에는 자동 복구되지 않는다.
  이 저장소에는 launchd 환경에서 claude CLI 인증이 끊겨 요약이 전부 비었던 사고 이력
  (`docs/superpowers/plans/2026-08-03-fix-launchd-claude-auth.md`)이 있다. 같은 성격의 위험이다.
- **일부 링크는 소스 추가에 실패한다.** 확인 중 `toss.tech` 는 빨간색으로 표시되며 소스로 잡히지 않았다.
  크롤링을 막는 사이트가 있다. 이때도 나머지 링크로 오디오는 생성된다.
- **노트북은 매일 새로 만든다.** 한 노트북에 계속 쌓으면 소스가 무한히 늘어나기 때문이다.
  대신 노트북 목록이 날마다 늘어나므로 주기적으로 정리하는 편이 낫다.
- **UI 셀렉터에 의존한다.** Gemini Notebook UI 가 바뀌면 `notebooklm.py` 의 `_L` 딕셔너리를
  고쳐야 한다. 한국어·영어 라벨을 모두 넣어두었다.
- 브라우저 자동화는 Google 서비스 약관에 저촉될 소지가 있다. 개인 용도 범위에서 판단해 쓸 것.
