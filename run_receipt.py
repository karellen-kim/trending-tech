"""실행 결과와 LLM 호출 상태를 원문 없이 실행별 원자 영수증으로 보존한다."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import uuid4

_current_run = None


def record_stage(name: str, status: str, **evidence) -> None:
    """실행 중 게시 함수가 확정한 중간 증거를 최상위 영수증에 연결한다."""
    if _current_run is not None:
        _current_run.stage(name, status, **evidence)


def record_llm_event(event: str, fields: dict) -> str | None:
    """현재 실행에 호출 ID와 상태만 연결하고 로그에 쓸 실행 ID를 반환한다."""
    run = _current_run
    if run is None:
        return None
    if event in ('llm_call_started', 'llm_call_finished'):
        with run.lock:
            run.state['llm_calls'][fields['call_id']] = (
                'running' if event == 'llm_call_started' else fields['status'])
            run.persist()
    return run.state['run_id']


class RunReceipt:
    """시작만 남은 실행과 종료된 실행, 게시 단계를 구분한다. 한 프로세스에 한 실행만 허용한다."""

    def __init__(self, directory: Path, day: str):
        self.lock = RLock()
        self.path = directory / f'{uuid4().hex}.json'
        self.outcome = 'partial'
        self.state = {
            'run_id': self.path.stem, 'date': day, 'process_id': os.getpid(),
            'started_at': datetime.now(timezone.utc).isoformat(),
            'finished_at': None, 'exit_code': None, 'status': 'running',
            'llm_calls': {}, 'source_status': {},
            'stages': {name: {'status': 'not_started'} for name in
                       ('collection', 'summary', 'artifacts', 'git', 'slack')},
        }

    def __enter__(self):
        """네트워크·요약 작업보다 먼저 시작 영수증을 확정한다."""
        global _current_run
        if _current_run is not None:
            raise RuntimeError('A daily run is already active')
        self.persist()
        _current_run = self
        print(f"[Run] {self.state['run_id']} started", flush=True)
        return self

    def persist(self) -> None:
        """같은 디렉터리의 fsync한 임시 파일로 기존 영수증을 원자 교체한다."""
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                        prefix='.run-', delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(self.state, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def stage(self, name: str, status: str, **evidence) -> None:
        """검증된 단계 결과만 저장하며 후속 단계와 구분한다."""
        with self.lock:
            self.state['stages'][name] = {'status': status, **evidence}
            self.persist()

    def sources(self, source_status: dict) -> None:
        """수집기가 반환한 선택 소스 누락 상태를 보존한다."""
        with self.lock:
            self.state['source_status'] = source_status
            self.persist()

    def require_finished_llm(self) -> None:
        """시작만 남은 호출이 있으면 산출물 게시와 성공 판정을 막는다."""
        with self.lock:
            if 'running' in self.state['llm_calls'].values():
                raise RuntimeError('Unfinished LLM calls prevent publication')

    def __exit__(self, error_type, error, traceback):
        """예외 본문 없이 최상위 종료와 마지막 단계 상태를 보존한다."""
        global _current_run
        try:
            with self.lock:
                if error is None:
                    self.state.update(status=self.outcome, exit_code=0)
                else:
                    code = 130 if isinstance(error, KeyboardInterrupt) else 1
                    if isinstance(error, SystemExit):
                        code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
                    status = 'interrupted' if isinstance(error, (SystemExit, KeyboardInterrupt)) else 'failed'
                    self.state.update(status=status, exit_code=code, error_type=error_type.__name__)
                    for stage in self.state['stages'].values():
                        if stage['status'] == 'running':
                            stage['status'] = status
                self.state['finished_at'] = datetime.now(timezone.utc).isoformat()
                self.persist()
                print(f"[Run] {self.state['run_id']} {self.state['status']} exit={self.state['exit_code']}", flush=True)
        finally:
            _current_run = None
