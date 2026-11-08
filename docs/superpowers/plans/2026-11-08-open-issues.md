# 열린 배치 이슈 수정

범위: #1 완료 신호 지연, #5 Reddit429, #11 Reddit 연결 실패, #12 Git 이후 Slack 실패.
확인: 11월6일 배치는 실제 partial/exit0/Git·Slack성공이지만 Mac 절전으로 10시간 이상 걸려 Orca6시간감시 종료. 7일 배치는 Git성공 후 Slack RequestException이나 기존 코드가 예외종류를 삭제했다. Reddit 응답은 remaining0/reset56초인데 현재1초 간격 및2초 backoff로 제한창 안에 다시 요청한다.

변경 흐름:
- supervisor → macOS caffeinate -i -s -w supervisorPID 실행 → worker 실행·대기 → guard 종료. 다른 OS는 기존 동작. 화면/사용자 강제절전·덮개 닫기는 보장하지 않으며 시스템 전역 설정은 변경하지 않는다.
- Reddit GET → 성공 응답 remaining0/reset도 공유 cooldown에 반영 → 다음 소스는 서버제한 대기. 429는 Retry-After/reset 중 긴 유효시간을 사용하며 총 대기360초·기존 요청예산 유지. ConnectionError/Timeout은 예산 내 대기 후 한번 재시도 가능; TLS·잘못된피드는 재시도하지 않는다. 오류는 예외종류만 기록하며 원문URL/본문을 기록하지 않는다. 대기가 예산을 넘으면 부분수집 유지.
- Slack POST → ConnectTimeout 또는 HTTP429만 최대3시도/총30초 대기 → HTTP200 수신증거. ReadTimeout/ConnectionError/5xx는 delivery_state unknown으로 남기고 재전송하지 않음. receipt에 시도수·오류분류·수신상태만 기록, webhook/원문예외 숨김. 기존 실패는 삭제하지 않는다.

검증: 절전 guard 시작/종료/비macOS, Reddit 성공quota0/reset과429reset/backoff 및 연결실패재시도·예산/공유상태, Slack 안전재시도/애매한실패단일전송/비밀정보 비노출 회귀 테스트. 기존 전체 테스트. 외부제한·실제야간예약은 결과를 구분해 보고하고 미검증 이슈를 성급히 닫지 않는다.

검증 결과: 실제 Reddit 6개 소스 모두 HTTP200, 총8요청(경계429 두 번 회복), 약292초 소요/287초 대기. 최종 게시 선택 최대3개는 기존대로 유지한다. macOS 실제 전원 assertion에서 자동절전 방지 활성화·해제를 확인했다. Slack 이력 조회로 7일 메시지가 이미 도착한 사실을 확인하여 재전송하지 않았다. 원본 실패 영수증은 보존했다. 실제 강제절전 원인은 ClamshellSleep이며 덮개를 닫은 야간 실행까지 해결된 것으로 보지 않는다.
