# NotebookLM 오디오 리뷰 설정

매일 하이라이트 5건의 원문 링크를 NotebookLM 노트북에 올리고 Audio Overview 를 만들어
`docs/audio/{날짜}.mp3` 로 저장한다. 일별 페이지 하이라이트 섹션에 재생기가 붙는다.

**기본은 꺼져 있다.** 아래 준비를 마치고 `.env` 에 `ENABLE_NOTEBOOKLM=1` 을 넣어야 동작한다.

## 왜 별도 서버가 필요한가

소비자용 NotebookLM(notebooklm.google.com)에는 공개 API 가 없다.
공식 API 는 [Gemini Notebook Enterprise](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-audio-overview)
에만 있고 Gemini Enterprise 라이선스가 필요하며 아직 Preview(`v1alpha`) 다.

그래서 [notebooklm-podcast-automator](https://github.com/israelbls/notebooklm-podcast-automator)
를 쓴다. Playwright 로 실제 브라우저를 띄워 NotebookLM UI 를 조작하고 그 위에 REST API 를 얹은 도구다.

## 준비 (최초 1회)

### 1. 자동화 서버 설치

```bash
git clone https://github.com/israelbls/notebooklm-podcast-automator.git
cd notebooklm-podcast-automator
uv sync                      # 또는 pip install -e .
playwright install chromium
```

### 2. NotebookLM 에서 노트북 만들기

이 도구는 **노트북을 새로 만들지 않는다.** notebooklm.google.com 에서 노트북을 하나 만들고
주소창의 URL 을 복사해둔다. 매일 같은 노트북의 소스를 비우고 새로 채우는 방식이다.

### 3. 서버 기동 + Google 로그인

```bash
NOTEBOOKLM_URL="<복사한 노트북 URL>" python -m notebooklm_automator.main
```

첫 실행에서 `~/.notebooklm-chrome` 프로필로 Chrome 창이 열린다. **그 창에서 Google 로그인**을 하면
세션이 프로필에 저장된다. 서버는 `http://localhost:8000` 에 뜨고 `/docs` 에서 Swagger 를 볼 수 있다.

### 4. 이 저장소 설정

`.env` 에 추가한다 (직접 편집):

```
ENABLE_NOTEBOOKLM=1
```

필요하면 함께 조정한다:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NOTEBOOKLM_API_URL` | `http://127.0.0.1:8000` | 자동화 서버 주소 |
| `NOTEBOOKLM_STYLE` | `deep_dive` | `summary` / `deep_dive` / `criticism` / `debate` |
| `NOTEBOOKLM_LANGUAGE` | `ko` | 오디오 언어 |
| `NOTEBOOKLM_TIMEOUT` | `900` | 생성 대기 상한(초) |
| `NOTEBOOKLM_POLL_INTERVAL` | `15` | 상태 폴링 간격(초) |

### 5. 실행

```bash
python main.py
```

## 동작 순서

```
하이라이트 5건 선정 (번호|요약 형식으로 받아 원문 URL 매핑)
  → POST /sources/clear      지난 소스 비우기
  → POST /sources/upload     링크 5건 업로드
  → POST /audio/generate     오디오 생성 시작 → job_id
  → GET  /audio/status/{id}  15초마다 폴링 (최대 15분)
  → GET  /audio/download/{id} → docs/audio/{날짜}.mp3
```

## 알아둘 것

- **오디오 생성 실패는 배치를 멈추지 않는다.** 서버가 꺼져 있거나 세션이 만료돼도
  HTML 생성·커밋·푸시는 정상으로 끝나고 그날 페이지에 재생기만 안 붙는다.
- **세션 만료 시 사람이 다시 로그인해야 한다.** launchd 무인 실행 중에는 자동 복구되지 않는다.
  이 저장소에는 launchd 환경에서 claude CLI 인증이 끊겨 요약이 전부 비었던 사고 이력
  (`docs/superpowers/plans/2026-08-03-fix-launchd-claude-auth.md`)이 있다. 같은 성격의 위험이다.
- **노트북은 하나를 재사용한다.** 어제 소스는 매번 지워진다. 보관이 필요하면 다른 노트북을 쓸 것.
- **mp3 가 저장소에 쌓인다.** 한 편에 수 MB 다. 오래된 파일을 정리하거나
  `.gitignore` 에 `docs/audio/` 를 넣고 다른 곳에 호스팅하는 선택지가 있다.
- 브라우저 자동화는 Google 서비스 약관에 저촉될 소지가 있다. 개인 용도 범위에서 판단해 쓸 것.
