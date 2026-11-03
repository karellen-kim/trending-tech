# 입력 부족과 요약 실패를 구분하고 실행 종료를 일치시킨다

유형: bugfix. 연결 이슈: https://github.com/karellen-kim/trending-tech/issues/7

필수 요약 누락은 계속 게시를 차단한다. 모델이 입력 부족 상태와 사유를 명시한 항목만 제목·링크를 유지한다. 이 경우 배치는 부분 완료로 기록한다.

## 발생 내역과 근거

- 2026-11-02 23:59:26 KST: `fc8bcc46562d4251aedd0d04e43f0cbf` 실행에서 Not A Copier 분석 호출이 success로 끝났지만 `Required summary is empty`로 전체 요약이 실패했다. 산출물·Git·Slack은 not_started였다.
- 23:59:26 이후: 이미 실행 중이던 다음 호출이 23:59:43에 끝났다. 영수증 확정 뒤라 종료 이벤트의 run_id는 null이고 영수증에는 running이 남았다.
- `summarizer.py::analyze_item`의 두 프롬프트는 입력 부족 시 빈 요약을 허용한다. `main.py::_analyze_items`는 본문 길이 150자 이상이면 입력의 실제 정보량과 무관하게 빈 요약을 거부한다.
- `supervisor.py::validate_receipt`는 실제 코드가 비정상이면 두 코드가 일치해도 process_exit_mismatch로 분류한다.
- 당시 모델 입력·응답 원문은 보존되지 않았다. 실제 글이 구독 안내였는지, 모델이 단순 누락했는지는 미확인이다. 새 테스트 입력은 재현용 fixture다.

## 목표와 영향 범위

입력 부족은 항목별로 명시하고 나머지 자료 처리를 계속한다. 응답 손상과 설명 없는 필수 요약 공백은 게시하지 않는다. 정상 실패 종료 시 호출 상태를 먼저 확정한다. 과거 게시물·배치 일정·모델·타임아웃·재시도 횟수·수집기는 바꾸지 않는다.

## 데이터 흐름과 수정

| 수행 위치 | 입력 | 처리 | 저장·출력 | 변경 |
|---|---|---|---|---|
| summarizer.py::analyze_item | 긴 비정보성 본문 + 모델 JSON | summary_status=insufficient_content, 비어 있지 않은 summary_reason, 빈 summary 조합 검증 | 번역·상태·사유 반환 | 수정 |
| main.py::_analyze_items | 검증된 분석 결과 | 명시적 입력 부족만 빈 요약 허용, 그 밖의 기존 필수 검사 유지 | 항목의 summary_status/summary_reason, summary_unavailable 로그 | 수정 |
| main.py::_run_daily | 항목별 결과 | 입력 부족 수를 영수증 summary 단계에 기록 | 정상 산출물·게시, 누락이 있으면 partial | 수정 |
| renderer.py::render_daily_page | 입력 부족인 빈 요약과 원문 | 논문·GitHub의 원문 대체 표시를 이 상태에서만 생략 | 번역 제목·링크 유지, 원문 데이터는 보존 | 수정 |
| main.py::_analyze_items 오류 경로 | 실패 Future와 실행 중인 호출 | 대기 Future 취소 후 실행 중 worker 종료를 기다림 | 호출 종료 기록 후 원래 예외 전파 | 수정 |
| supervisor.py::validate_receipt | OS 코드 1, 영수증 코드 1 | 코드 비교와 업무 실패 판정 분리 | unsuccessful_receipt; 0/1은 process_exit_mismatch | 수정 |

예시 JSON은 설계 예시다.

```json
{"is_today":true,"title_ko":"예시 제목","summary":"","summary_status":"insufficient_content","summary_reason":"본문 대신 구독 안내만 제공됨"}
```

이 항목은 제목·링크만 남는다. summary 상태와 사유는 일간 JSON의 summary_omissions에 섹션·제목·URL과 함께 저장한다. 전체 영수증의 summary 단계는 성공과 누락 수를 기록한다. Git·Slack이 성공해도 입력 부족 항목이 있으면 최종 상태는 partial이다. 감독기도 누락이 있는 published 영수증을 거부한다. 자료가 정상이고 summary가 비었거나 사유가 없으면 기존 실패 경로로 간다.

정상 비어 있지 않은 기존 응답은 summary_status 필드가 없어도 호환한다. 입력 부족 상태는 요약을 포함할 수 없다. 날짜 제외 항목과 기존 짧은 본문·제목 전용 항목의 규칙은 유지한다.

## 재발 방지와 검증

- 테스트: 긴 비정보성 입력의 명시적 입력 부족, 정상 요약, 설명 없는 공백, 잘못된 상태·타입·사유 조합을 두 프롬프트 경로에서 검증한다.
- 테스트: 실제 ThreadPoolExecutor와 Event로 실패 중 다른 worker가 실행되는 순서를 고정한다. 최종 영수증 확정 전에 두 호출 종료가 연결되는지 검사한다. 무제한 sleep을 쓰지 않는다.
- 테스트: 입력 부족이 있는 게시 결과가 partial인지, 필수 오류는 여전히 산출물·Git·Slack을 차단하는지 검증한다. 감독기의 1/1·0/1·1/0 코드 조합을 구분한다.
- 가드·관측: 명시적 상태와 사유 없이는 빈 필수 요약을 통과시키지 않는다. 원문 없는 summary_unavailable 이벤트와 영수증 누락 수로 의도된 생략을 확인한다.

## 제한과 되돌리기

worker 종료 대기로 실패 반환이 현재 호출의 제한 시간 600초까지 늦어질 수 있다. 프로세스를 조기 취소하는 새 장치는 추가하지 않는다. SIGKILL이나 정리 중 재차 강제 종료는 기존대로 미완료 기록을 남길 수 있다. 실제 종료를 확인하지 않고 running을 cancelled로 바꾸지 않는다.

오래된 당일 페이지를 현재 입력으로 재발행하지 않는다. 실제 운영 수집·모델 응답 품질·Git·Slack 전체 경로는 다음 예약에서 별도 확인한다. 코드와 계획을 하나의 PR로 되돌릴 수 있다.
