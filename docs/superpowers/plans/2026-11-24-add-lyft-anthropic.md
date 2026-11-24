# Lyft와 Anthropic 회사 블로그 등록

목표: Lyft Engineering과 Anthropic Engineering·News를 기존 기술 블로그 수집·요약·게시 경로에 포함한다. Lyft 공식 RSS는 HTTP200/10항목/발행일·본문이 있어 기존 RSS수집기에 등록한다. Anthropic 공식 Engineering/News는 RSS연결이 없고 확인한 RSS경로가404이므로 목록·본문 전용 파서를 추가한다.

흐름:
- Lyft RSS → 기존 날짜필터와 본문 보강 → company항목 → 기존7일중복제거·25건상한·요약·HTML/Slack.
- Anthropic 목록 → 기사링크와 발행일 추출·중복제거·최근2일 날짜검증 → 소스당최대3개 원문조회 → 기사제목/메타발행일/본문추출 → 같은 company계약(title,url,source,summary,content,pub_hint,date_verified,pub_date). 날짜 없는·미래·기간밖 글은 포함하지 않는다. featured/관련글/전역페이지날짜를 기사날짜로 오인하지 않는다.

구현: sources/anthropic.py에공통파서+Engineering/News 진입함수, 기존scraperregistry에연결, config에Lyft RSS와Anthropic2소스등록. 기존수집옵션/회사상한/LLM모델/기존게시물은변경하지않는다. RSS없는소스의네트워크·목록형식오류는기존Scraper로그에남긴다. 신규의존성없음.

검증: 실제피드/HTML에서선별한작은fixture로최근·과거·미래·누락날짜·고정글의순서·중복·본문영역·실패·요청상한·등록계약을검증. 먼저실패테스트, 구현후전체테스트, 독립리뷰. 실제HTTP로Lyft RSS와Anthropic각목록·원문제목/날짜/본문검증, 과거발행일로읽기전용수집확인. Git/Slack/Notebook재게시없이코드push로다음정기수집적용.
