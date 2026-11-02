# 일일 실행 결과 확인

`main.py`는 실행마다 `logs/runs/<run_id>.json`에 시작과 종료 결과를 남겨요. Orca의 `completed`나 마지막 콘솔 문구만으로 게시 완료를 판단하지 마세요.

`python -u main.py`는 감독 프로세스가 일일 Python 자식을 한 번 실행하는 진입점이에요. 기존 자동화 명령을 그대로 사용할 수 있어요. 자식의 stdout·stderr는 `logs/runs/<run_id>.log`로 모으고, 감독 stdout에는 자식 종료 후 `event=daily_run_finished`인 JSON 한 줄만 출력해요. 숫자나 `ready` 같은 자식 출력은 완료 신호가 아니에요.

최종 JSON의 `run_id`, `receipt_path`, `log_path`로 같은 실행을 찾아요. `process_exit_code`는 감독이 관측한 자식의 OS 종료 코드, `receipt_exit_code`는 업무가 영수증에 기록한 코드예요. 신호로 종료되면 OS 코드는 음수일 수 있어요. `stages`에는 수집·요약·산출물 상태와 Git 커밋·push, Slack HTTP 상태가 포함돼요. 원문과 예외 메시지는 최종 JSON에 넣지 않아요.

감독은 run ID·자식 PID·날짜·종료 시각·코드가 일치하는 정확한 영수증만 검증해요. 자식 종료 코드가 0이어도 영수증이 없거나 손상됐거나 `running/failed/interrupted`이면 감독은 실패 코드 1을 반환해요. 자식 비정상 코드는 보존하며 음수 신호 코드는 `128+신호 번호`로 반환해요. 감독이 SIGTERM/SIGINT를 받으면 자식에 전달해 회수하고 자신도 중단 코드로 종료해요. 이미 실행 중인 요약 스레드가 남아 있으면 Codex의 600초 제한까지 종료가 지연될 수 있고, 그동안 최종 JSON은 없어요.

Python에서 `main.main()`을 직접 호출하면 기존 업무 함수만 실행해요. 이 경우 콘솔의 `[Run] <run_id> started`에서 실행 ID를 찾아요. 같은 이름의 JSON에서 `date`, `started_at`, `process_id`를 실행 도구의 시작 시각·업무 자식 PID와 대조해요. 시각은 UTC예요. 같은 날짜에 실행이 여러 번 있으면 날짜만으로 영수증을 고르지 마세요.

| status | 의미 |
| --- | --- |
| `running` | 시작만 확인됐어요. `exit_code`와 `finished_at`은 null이에요. |
| `published` | 필수 요약 검증, 당일 JSON·HTML 저장, Git push, Slack HTTP 200을 확인했어요. HN·Reddit 수집도 성공했어요. |
| `partial` | 배치는 종료됐지만 선택 소스가 누락됐거나 Slack 설정이 없어 게시 확인이 빠졌어요. |
| `dry_run` | 산출물 생성까지 확인했어요. Git과 Slack은 건너뛰었어요. |
| `failed` | 예외로 실패했어요. 마지막 단계와 `error_type`을 확인하세요. |
| `interrupted` | SIGTERM, 키보드 중단 또는 6시간 타임아웃으로 중단됐어요. |

`exit_code=0`은 Python 흐름이 정상 반환됐다는 뜻이에요. `partial`과 `dry_run`도 0일 수 있으므로 게시 완료는 `status`와 단계별 증거를 함께 확인해야 해요. 감독은 `published`를 보고하기 전에 필수 단계 성공, Git 커밋·push, Slack HTTP 200, 선택 소스 성공, 미완료 LLM 부재도 검증해요. 영수증과 OS 종료가 맞지 않으면 `validation_error`와 함께 실패로 보고해요.

`stages`는 수집, 요약, 산출물, Git, Slack을 구분해요. Git 커밋 뒤 push가 실패해도 커밋 SHA와 `pushed=false`가 남아요. Git 성공 뒤 Slack이 실패하면 Git 성공과 Slack 실패가 따로 남아요. 이 상태에서 자동으로 재실행하면 중복 게시될 수 있어요.

Git 증거는 `stages.git.status`, `commit_sha`, `committed`, `pushed`예요. Slack 수신 확인은 `stages.slack.status=success`, `http_status=200`이에요. 두 게시가 성공했어도 선택 소스 누락만으로 `partial`이 될 수 있어요. 게시 결과가 불명확하면 영수증의 실행 ID와 단계 상태를 운영자에게 전달하고 기존 원격 커밋·Slack 메시지를 먼저 확인하세요.

LLM 로그에는 `run_id`를 붙여요. 영수증의 `llm_calls`는 호출 ID별 상태만 보관해요. 값이 `running`인 호출이 있으면 게시와 정상 완료를 막아요. 배치가 실패한 시점에 worker가 남아 있으면 최상위 실패와 미완료 호출이 함께 남을 수 있어요.

SIGKILL이나 호스트 장애는 종료 기록을 남길 수 없어요. `running`만 남은 실행이나 감독 최종 JSON이 없는 실행은 미완료예요. 종료 코드나 성공을 추정하지 마세요. 이 저장소의 변경은 외부 Orca 감시기의 판정 로직까지 바꾸지 않아요.

[이슈 #3](https://github.com/karellen-kim/trending-tech/issues/3)의 신호 발신자와 Orca 완료 판정 원인은 미확인이에요. Orca 운영 담당자가 원 실행 `4b21a90e-de43-4a4e-8ccd-ba7f73d56a5e`와 연결 세션 `01a18d4e-d687-7401-b93e-1f8a997ecb74`의 2026-10-30 23:55:57~59 KST 완료 이벤트·터미널 종료·프로세스 종료 이벤트를 대조해야 해요. 이 저장소에는 그 이벤트를 조회하거나 Orca 판정을 수정하는 코드가 없어요. 이번 수정에서는 운영 실행을 하지 않았어요. 다음 자연 예약에서는 감독 JSON, 도구 종료 코드, 동일 실행의 영수증과 게시 증거를 대조해야 해요.

수집과 요약 정책은 다음과 같아요.

- GitHub·블로그·논문·스크레이퍼의 수집 함수가 예외를 내거나 필수 요약 검증이 실패하면 게시를 중단해요. 기존 수집기 내부에서 삼키는 개별 피드 오류까지 모두 검증했다는 뜻은 아니에요.
- HN·Reddit은 선택 소스예요. 수집 실패가 있어도 산출물을 만들되 최종 상태를 `partial`로 남겨요. `source_status`는 실행 영수증과 당일 JSON에 보존돼요.
- Reddit은 subreddit별 성공·실패·수집 수·요청 횟수·HTTP 상태·재시도 대기를 기록해요. 정상 빈 피드와 요청 실패를 구분해요.
- 429는 subreddit당 최대 3회 요청해요. 재시도 대기는 Reddit 전체에서 최대 30초예요. 기존 subreddit 사이 1초 간격과 요청당 최대 15초는 이 재시도 대기 예산과 별도예요.
- `Retry-After`가 있으면 초 또는 HTTP 날짜로 읽어요. 없거나 잘못되면 2초, 4초 backoff를 써요. 대기 예산을 넘거나 429 재시도를 소진하면 남은 subreddit은 `skipped_rate_limit`로 남겨요. 오래된 캐시는 재사용하지 않아요.

`Retry-After` 형식은 [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)을 따랐어요. 429 응답의 이 헤더는 [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)에서 선택 사항이에요.

영수증은 동일 디렉터리의 임시 파일을 fsync한 뒤 원자 교체해요. 영수증에는 원문·프롬프트·webhook·응답 본문·예외 메시지를 저장하지 않아요. 자식 로그 파일에는 기존 콘솔 진단이 있으므로 외부 보고에는 필요한 상태만 발췌해요. 기존 로그와 영수증은 보존하세요. 코드 롤백과 진단 파일 삭제는 별개예요.

회귀 테스트는 `python -m pytest -q`로 실행할 수 있어요. 테스트는 HTTP 호출과 게시를 모의 처리하고 진단·산출물을 임시 디렉터리로 격리해요. 신호 테스트도 수집을 대기 함수로 교체한 자식 프로세스만 종료해요. 운영 배치 재실행, 실제 모델·Reddit·Git·Slack 검증은 포함하지 않아요.
