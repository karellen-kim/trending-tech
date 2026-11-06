# 배치 게시와 예약 날짜 복구

11월 3~5일 예약 실행은 요약·산출물 성공 후 원격 변경 때문에 push가 거절됐다. 로컬에 PR8·10이 없어 복구 코드가 실행되지 않았다. 자정 뒤 실행된 3·5일분은 실제 시작일 4·6일로 저장됐다.

목표: 기존 산출물과 사용자 파일을 보존하며 게시를 복구하고, 3·5일 자료를 역사적 날짜로 소급 생성한다.

입력 → 처리 → 저장 → 출력:
- 예약 실행: Orca scheduledFor의 KST 날짜를 RUN_DATE로 전달 → supervisor가 ISO 날짜 검증 후 기존 worker에 전달 → 같은 날짜 receipt/HTML/JSON → 날짜가 바뀌어도 예약일 유지. 수동 CLI는 환경변수 없으면 현재 날짜.
- 게시: docs 커밋 → push 거절 → 추적 파일만 clean 검사 → 기존 PR10 rebase/push → Slack. 미추적 파일은 그대로 두며 충돌은 Git이 거절하고 rebase abort. 인증 오류는 재시도하지 않는다.
- 복구: 이미 생성된 4·6일 HTML 보존/기존 커밋 동기화 → Git push 확인 → 날짜별 Slack 한 번과 보충 receipt. 3·5일은 발행일 확인 RSS·전날 HN·당일 arXiv로 생성하고 역사적 GitHub/Reddit 미복원 명시.

검증: 실제 bare Git remote에서 원격 진전+미추적 파일 보존, 추적 수정 차단, 미추적 충돌 보존. supervisor RUN_DATE 전달·잘못된 날짜 거부·기본 현재 날짜. 기존 전체 테스트 및 실제 날짜별 공개 페이지/Git/Slack/Notebook 링크 확인.
재발 방지: 위 회귀 테스트와 날짜 입력 검증, 같은 run_id receipt 게시 증거 유지. 실패 원본은 변경하지 않고 보충 영수증으로 복구 기록.
