"""일일 자식 프로세스 종료와 동일 실행 영수증을 대조해 최종 결과만 출력한다."""
import json
import re
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from config import LOGS_DIR, now_kst


def validate_receipt(state: dict, run_id: str, pid: int, day: str,
                     process_code: int) -> str | None:
    """성공 문자열 대신 실행 식별자·종료·단계별 게시 증거를 검증한다."""
    if not isinstance(state, dict):
        return 'invalid_receipt'
    if (state.get('run_id'), state.get('process_id'), state.get('date')) != (run_id, pid, day):
        return 'receipt_identity_mismatch'
    if not state.get('started_at') or not state.get('finished_at'):
        return 'unfinished_receipt'
    if process_code != 0 or state.get('exit_code') != process_code:
        return 'process_exit_mismatch'
    status = state.get('status')
    if status not in ('published', 'partial', 'dry_run'):
        return 'unsuccessful_receipt'
    calls, stages, sources = (state.get(key) for key in ('llm_calls', 'stages', 'source_status'))
    if not isinstance(calls, dict) or 'running' in calls.values():
        return 'unfinished_llm_calls'
    if not isinstance(stages, dict) or not all(
            isinstance(stages.get(name), dict) for name in
            ('collection', 'summary', 'artifacts', 'git', 'slack')):
        return 'invalid_stages'
    if any(stages[name].get('status') != 'success' for name in ('collection', 'summary', 'artifacts')):
        return 'incomplete_required_stages'
    git, slack = stages['git'], stages['slack']
    if status == 'dry_run':
        if any(stage.get('status') != 'skipped' or stage.get('reason') != 'dry_run'
               for stage in (git, slack)):
            return 'invalid_dry_run'
        return None
    if (git.get('status') != 'success' or git.get('committed') is not True
            or git.get('pushed') is not True
            or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', str(git.get('commit_sha', '')))):
        return 'unconfirmed_git_publication'
    slack_success = slack.get('status') == 'success' and slack.get('http_status') == 200
    if status == 'partial':
        if not slack_success and slack != {'status': 'skipped', 'reason': 'not_configured'}:
            return 'unconfirmed_slack_publication'
    elif not slack_success:
        return 'unconfirmed_slack_publication'
    if not isinstance(sources, dict) or (status == 'published' and any(
            not isinstance(source, dict) or source.get('status') != 'success' for source in sources.values())):
        return 'incomplete_sources'
    return None


def supervise(command: list[str], directory: Path, day: str) -> int:
    """자식 출력은 파일로 격리하고 wait 이후 검증 결과 한 줄과 OS 코드를 반환한다."""
    run_id = uuid4().hex
    directory = directory.resolve()
    receipt_path, log_path = directory / f'{run_id}.json', directory / f'{run_id}.log'
    result = {'event': 'daily_run_finished', 'run_id': run_id, 'date': day,
              'status': 'failed', 'process_exit_code': None, 'receipt_exit_code': None,
              'receipt_path': str(receipt_path), 'log_path': str(log_path), 'stages': {}}
    process, interrupted = None, None

    def forward(signum, frame):
        nonlocal interrupted
        interrupted = interrupted or signum
        if process is not None and process.poll() is None:
            try:
                process.send_signal(signum)
            except ProcessLookupError:
                pass

    handlers = {sig: signal.signal(sig, forward) for sig in (signal.SIGTERM, signal.SIGINT)}
    code = 1
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with log_path.open('x', encoding='utf-8') as log:
            if interrupted is None:
                process = subprocess.Popen([*command, run_id], stdout=log, stderr=subprocess.STDOUT)
                if interrupted is not None:
                    forward(interrupted, None)
                process_code = process.wait()
                result['process_exit_code'] = process_code
                code = process_code if process_code >= 0 else 128 - process_code
                try:
                    state = json.loads(receipt_path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    state = None
                error = validate_receipt(state, run_id, process.pid, day, process_code)
                if isinstance(state, dict) and (state.get('run_id'), state.get('process_id'), state.get('date')) == (run_id, process.pid, day):
                    result['receipt_exit_code'] = state.get('exit_code')
                    # Only known publication metadata is emitted; no raw worker output or exception text.
                    if isinstance(state.get('stages'), dict):
                        result['stages'] = {
                            name: {key: value for key, value in stage.items() if key in
                                   ('status', 'commit_sha', 'committed', 'pushed', 'http_status', 'reason')}
                            for name, stage in state['stages'].items()
                            if name in ('collection', 'summary', 'artifacts', 'git', 'slack') and isinstance(stage, dict)}
                    if state.get('status') == 'interrupted':
                        result['status'] = 'interrupted'
                if error:
                    result['validation_error'] = error
                    code = code or 1
                else:
                    result['status'] = state['status']
    except OSError:
        result['validation_error'] = 'supervisor_io_error'
        code = 1
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    if interrupted is not None:
        result['status'] = 'interrupted'
        code = 128 + interrupted
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


def main() -> int:
    """기존 main.py 명령에서 동일 Python으로 실제 일일 업무를 한 번 실행한다."""
    # Importing main keeps the existing callable API; the CLI parent alone supervises it.
    day = str(now_kst().date())
    script = (f'import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); '
              'from main import main; main(run_date=sys.argv[1], run_id=sys.argv[2])')
    return supervise([sys.executable, '-u', '-c', script, day], LOGS_DIR / 'runs', day)
