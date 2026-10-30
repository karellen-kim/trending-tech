"""실제 모의 자식만 사용해 최상위 종료와 영수증 검증을 확인한다."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
from unittest.mock import Mock

import pytest

import supervisor


DAY = '2026-10-30'


def completed_state(run_id, pid):
    return {
        'run_id': run_id, 'process_id': pid, 'date': DAY,
        'started_at': '2026-10-30T14:55:00+00:00',
        'finished_at': '2026-10-30T15:55:00+00:00',
        'exit_code': 0, 'status': 'published', 'llm_calls': {},
        'source_status': {},
        'stages': {
            'collection': {'status': 'success'}, 'summary': {'status': 'success'},
            'artifacts': {'status': 'success'},
            'git': {'status': 'success', 'commit_sha': 'a' * 40,
                    'committed': True, 'pushed': True},
            'slack': {'status': 'success', 'http_status': 200},
        },
    }


@pytest.mark.parametrize('status', ['published', 'partial', 'dry_run'])
def test_terminal_outcomes_keep_distinct_status(status):
    state = completed_state('a' * 32, 123)
    state['status'] = status
    if status == 'partial':
        state['stages']['slack'] = {'status': 'skipped', 'reason': 'not_configured'}
    elif status == 'dry_run':
        for stage in ('git', 'slack'):
            state['stages'][stage] = {'status': 'skipped', 'reason': 'dry_run'}
    assert supervisor.validate_receipt(state, 'a' * 32, 123, DAY, 0) is None


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(run_id='old-run'),
    lambda s: s.update(process_id=999),
    lambda s: s.update(date='2026-10-29'),
    lambda s: s.update(finished_at=None),
    lambda s: s.update(exit_code=143),
    lambda s: s.update(status='running'),
    lambda s: s.update(status='interrupted'),
    lambda s: s.update(status='failed'),
    lambda s: s.update(llm_calls={'unfinished': 'running'}),
    lambda s: s['stages']['git'].update(pushed=False),
    lambda s: s['stages']['git'].update(commit_sha=''),
    lambda s: s['stages']['summary'].update(status='running'),
    lambda s: s['stages']['slack'].update(http_status=500),
    lambda s: s.update(stages=[]),
    lambda s: s.update(source_status={'reddit': {'status': 'failed'}}),
])
def test_zero_exit_and_status_string_cannot_override_evidence(mutate):
    state = completed_state('a' * 32, 123)
    mutate(state)
    assert supervisor.validate_receipt(state, 'a' * 32, 123, DAY, 0)


@pytest.mark.parametrize('state', [None, [], {}, {'stages': None}])
def test_invalid_receipt_is_rejected(state):
    assert supervisor.validate_receipt(state, 'a' * 32, 123, DAY, 0)


def test_existing_main_command_uses_supervisor(monkeypatch):
    import runpy
    entry = Mock(return_value=17)
    monkeypatch.setattr(supervisor, 'main', entry)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(supervisor.__file__).with_name('main.py')), run_name='__main__')
    assert error.value.code == 17
    entry.assert_called_once_with()


def test_explicit_run_id_reaches_exact_receipt(tmp_path):
    from run_receipt import RunReceipt
    with RunReceipt(tmp_path, DAY, run_id='a' * 32) as run:
        assert run.state['run_id'] == 'a' * 32
        assert run.path == tmp_path / ('a' * 32 + '.json')
    with pytest.raises(ValueError):
        RunReceipt(tmp_path, DAY, run_id='../escape')


def test_main_launches_same_interpreter_and_passes_fixed_day(tmp_path, monkeypatch, capsys):
    from datetime import datetime
    state = completed_state('unused', 0)
    # A local stub main validates the actual production command without any collection or publication.
    (tmp_path / 'main.py').write_text(
        'import json, os\nfrom pathlib import Path\n'
        'def main(*, run_date, run_id):\n'
        f' state = {state!r}\n'
        ' state.update(run_id=run_id, process_id=os.getpid(), date=run_date)\n'
        f' Path({str(tmp_path)!r}, "runs", run_id + ".json").write_text(json.dumps(state))\n',
        encoding='utf-8')
    monkeypatch.setattr(supervisor, '__file__', str(tmp_path / 'supervisor.py'))
    monkeypatch.setattr(supervisor, 'LOGS_DIR', tmp_path)
    monkeypatch.setattr(supervisor, 'now_kst', lambda: datetime(2026, 10, 30, 23, 59, 59))
    assert supervisor.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['date'] == DAY
    assert result['status'] == 'published'


def start_supervisor(tmp_path, mode):
    worker = tmp_path / 'worker.py'
    worker.write_text('''
import json, os, signal, sys, time
from pathlib import Path
from tests.test_supervisor import completed_state
directory, mode, run_id = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
state = completed_state(run_id, os.getpid())
path = directory / (run_id + '.json')
def interrupted(sig, frame):
    state.update(status='interrupted', exit_code=143)
    state['stages']['collection']['status'] = 'interrupted'
    path.write_text(json.dumps(state))
    raise SystemExit(143)
signal.signal(signal.SIGTERM, interrupted)
print('215,648,654', flush=True)
print('ready', file=sys.stderr, flush=True)
if mode == 'waiting':
    state.update(status='running', finished_at=None, exit_code=None)
    path.write_text(json.dumps(state))
    (directory / 'ready').write_text(str(os.getpid()))
    while not (directory / 'release').exists(): time.sleep(0.01)
    state = completed_state(run_id, os.getpid())
if mode == 'missing': pass
elif mode == 'invalid': path.write_text('invalid JSON secret')
else: path.write_text(json.dumps(state))
if mode == 'nonzero': raise SystemExit(7)
''', encoding='utf-8')
    # Only this isolated worker is launched; it cannot run the production pipeline.
    script = '''
import sys
from pathlib import Path
from supervisor import supervise
raise SystemExit(supervise([sys.executable, sys.argv[1], sys.argv[2], sys.argv[3]],
                          Path(sys.argv[2]), '2026-10-30'))
'''
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(Path(supervisor.__file__).parent))
    return subprocess.Popen([sys.executable, '-c', script, str(worker), str(tmp_path), mode],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def finish(process):
    stdout, stderr = process.communicate(timeout=10)
    assert not stderr, stderr.decode()
    lines = stdout.decode().splitlines()
    assert len(lines) == 1
    assert '215,648,654' not in lines[0] and 'ready' not in lines[0]
    return json.loads(lines[0])


def wait_ready(directory, process):
    import time
    deadline = time.monotonic() + 10
    while not (directory / 'ready').exists():
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_child_output_does_not_finish_supervisor(tmp_path):
    process = start_supervisor(tmp_path, 'waiting')
    try:
        wait_ready(tmp_path, process)
        assert process.poll() is None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert not selector.select(timeout=0.1), 'output before top-level exit'
        log = next(tmp_path.glob('*.log')).read_text()
        assert '215,648,654' in log and 'ready' in log
        (tmp_path / 'release').touch()
        result = finish(process)
        assert process.returncode == 0
        assert result['status'] == 'published'
        assert result['process_exit_code'] == result['receipt_exit_code'] == 0
        assert result['stages']['git']['pushed'] is True
        assert result['stages']['slack']['http_status'] == 200
        assert Path(result['receipt_path']).stem == result['run_id']
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)


@pytest.mark.parametrize('target, signum, code, status', [
    ('worker', signal.SIGTERM, 143, 'interrupted'),
    ('supervisor', signal.SIGTERM, 143, 'interrupted'),
    ('worker', signal.SIGKILL, 137, 'failed'),
])
def test_interruption_is_never_reported_as_success(tmp_path, target, signum, code, status):
    process = start_supervisor(tmp_path, 'waiting')
    try:
        wait_ready(tmp_path, process)
        pid = int((tmp_path / 'ready').read_text()) if target == 'worker' else process.pid
        os.kill(pid, signum)
        result = finish(process)
        assert process.returncode == code
        assert result['status'] == status
        if signum == signal.SIGKILL:
            assert result['process_exit_code'] == -9
            assert result['receipt_exit_code'] is None
        else:
            assert result['process_exit_code'] == result['receipt_exit_code'] == 143
            assert result['stages']['collection']['status'] == 'interrupted'
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)


@pytest.mark.parametrize('mode, code', [('missing', 1), ('invalid', 1), ('nonzero', 7)])
def test_failed_child_or_unusable_receipt_fails_closed(tmp_path, mode, code):
    process = start_supervisor(tmp_path, mode)
    result = finish(process)
    assert process.returncode == code
    assert result['status'] == 'failed'
    assert result['validation_error']
    assert 'secret' not in json.dumps(result)
