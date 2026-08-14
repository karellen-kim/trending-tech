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

### 2. 노트북 만들고 주소 확보

[notebook.google.com](https://notebook.google.com/) 에서 노트북을 하나 만들고 주소창 URL 을 복사한다.
매일 같은 노트북에 소스를 추가하는 방식이다.

```
https://notebook.google.com/notebook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 3. 로그인 (사람이 직접)

```bash
.venv/bin/python -m notebooklm login
```

Chrome 창이 열린다. Google 로그인을 마치고 터미널에서 Enter 를 누르면
세션이 `~/.gemini-notebook-profile` 에 저장된다. 이후로는 자동으로 이 세션을 쓴다.

### 4. `.env` 설정

```
ENABLE_NOTEBOOKLM=1
NOTEBOOKLM_NOTEBOOK_URL=https://notebook.google.com/notebook/<노트북 ID>
```

선택 설정:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NOTEBOOKLM_FORMAT` | `deep_dive` | `deep_dive`(심층 분석) / `summary`(요약) / `criticism`(비평) / `debate`(토론) |
| `NOTEBOOKLM_LANGUAGE` | `ko` | 오디오 언어 |
| `NOTEBOOKLM_PROFILE_DIR` | `~/.gemini-notebook-profile` | 로그인 세션 저장 위치 |
| `NOTEBOOKLM_HEADLESS` | `1` | `0` 이면 창을 띄운다 (문제 진단용) |
| `NOTEBOOKLM_TIMEOUT` | `120` | 페이지 로드 대기(초) |

### 5. 실행

```bash
.venv/bin/python main.py
```

## 동작 순서

실제 화면에서 확인한 흐름이다.

```
하이라이트 5건 선정 (번호|요약 형식으로 받아 원문 URL 매핑)
  → 노트북 URL 열기
  → "출처 추가" 클릭
  → "웹사이트" 클릭
  → URL 5건을 줄바꿈으로 구분해 한 번에 입력       ← 화면이 이 방식을 안내한다
  → "삽입" 클릭
  → 소스 크롤링 대기
  → "AI 오디오 오버뷰" 클릭
  → 형식 선택 + 집중할 내용 프롬프트 입력
  → "생성" 클릭 → "AI 오디오 오버뷰 생성 중..." 확인
```

## 알아둘 것

- **실패는 배치를 멈추지 않는다.** 로그인이 풀렸거나 UI 가 바뀌어도
  HTML 생성·커밋·푸시는 정상으로 끝나고 그날 페이지에 노트북 링크만 안 붙는다.
- **세션이 만료되면 사람이 다시 로그인해야 한다.** launchd 무인 실행 중에는 자동 복구되지 않는다.
  이 저장소에는 launchd 환경에서 claude CLI 인증이 끊겨 요약이 전부 비었던 사고 이력
  (`docs/superpowers/plans/2026-08-03-fix-launchd-claude-auth.md`)이 있다. 같은 성격의 위험이다.
- **일부 링크는 소스 추가에 실패한다.** 확인 중 `toss.tech` 는 빨간색으로 표시되며 소스로 잡히지 않았다.
  크롤링을 막는 사이트가 있다. 이때도 나머지 링크로 오디오는 생성된다.
- **노트북은 하나를 재사용한다.** 소스가 계속 누적되므로 주기적으로 정리하거나
  날짜별로 노트북을 나누는 편이 낫다.
- **UI 셀렉터에 의존한다.** Gemini Notebook UI 가 바뀌면 `notebooklm.py` 의 `_L` 딕셔너리를
  고쳐야 한다. 한국어·영어 라벨을 모두 넣어두었다.
- 브라우저 자동화는 Google 서비스 약관에 저촉될 소지가 있다. 개인 용도 범위에서 판단해 쓸 것.
