import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import summarizer


def _process(returncode=0, stdout='진행 로그', stderr=''):
    process = MagicMock(returncode=returncode)
    process.communicate.return_value = (stdout, stderr)
    return process


def test_codex_reads_only_final_message():
    process = _process()

    def popen(args, **kwargs):
        assert args[:2] == ['codex', 'exec']
        assert args[args.index('--model') + 1] == 'gpt-6.1-sol'
        assert args[args.index('--sandbox') + 1] == 'read-only'
        assert '--ephemeral' in args
        assert args[-1] == '-'
        assert kwargs['start_new_session'] is True
        Path(args[args.index('--output-last-message') + 1]).write_text('  {"summary":"결과"}  ')
        return process

    with patch('summarizer.subprocess.Popen', side_effect=popen):
        assert summarizer._run_codex('요약\x00 원문', timeout=60) == '{"summary":"결과"}'
    process.communicate.assert_called_once_with(input='요약 원문', timeout=60)


@pytest.mark.parametrize('failure', [FileNotFoundError('codex'), ValueError('bad input')])
def test_codex_failure_returns_empty(failure):
    with patch('summarizer.subprocess.Popen', side_effect=failure):
        assert summarizer._run_codex('prompt') == ''


def test_codex_nonzero_returns_empty():
    with patch('summarizer.subprocess.Popen', return_value=_process(1, stderr='error')):
        assert summarizer._run_codex('prompt') == ''


def test_codex_missing_response_returns_empty():
    with patch('summarizer.subprocess.Popen', return_value=_process()):
        assert summarizer._run_codex('prompt') == ''


def test_codex_default_timeout_is_ten_minutes():
    process = _process(1, stderr='error')
    with patch('summarizer.subprocess.Popen', return_value=process):
        summarizer._run_codex('prompt')
    assert process.communicate.call_args.kwargs['timeout'] == 600


def test_codex_batch_abort_kills_group_and_reraises():
    process = _process()
    process.pid = 12345
    process.communicate.side_effect = [SystemExit(1), ('', '')]
    with patch('summarizer.subprocess.Popen', return_value=process), \
            patch('summarizer.os.killpg') as killpg:
        with pytest.raises(SystemExit) as error:
            summarizer._run_codex('prompt')
    assert error.value.code == 1
    killpg.assert_called_once_with(process.pid, signal.SIGKILL)
    assert process.communicate.call_count == 2
    assert process.communicate.call_args.args == ()
    assert process.communicate.call_args.kwargs == {}


def test_codex_timeout_kills_launcher_and_child(tmp_path):
    child_pid_path = tmp_path / 'child.pid'
    heartbeat_path = tmp_path / 'heartbeat'
    child_script = (
        'import time; from pathlib import Path; '
        f'path = Path({str(heartbeat_path)!r}); '
        '\nwhile True:\n path.write_text(str(time.monotonic())); time.sleep(0.02)'
    )
    launcher = (
        'import subprocess, sys, time; '
        'from pathlib import Path; '
        f'child = subprocess.Popen([sys.executable, "-c", {child_script!r}]); '
        f'Path({str(child_pid_path)!r}).write_text(str(child.pid)); '
        'time.sleep(60)'
    )
    original_popen = subprocess.Popen
    processes = []

    def popen(args, **kwargs):
        process = original_popen([sys.executable, '-c', launcher], **kwargs)
        processes.append(process)
        return process

    child_pid = None
    try:
        with patch('summarizer.subprocess.Popen', side_effect=popen):
            assert summarizer._run_codex('prompt', timeout=1) == ''
        assert processes[0].poll() is not None
        child_pid = int(child_pid_path.read_text())
        heartbeat = heartbeat_path.read_text()
        time.sleep(0.15)
        assert heartbeat_path.read_text() == heartbeat, 'native child survived the timeout'
    finally:
        if child_pid is None and child_pid_path.exists():
            child_pid = int(child_pid_path.read_text())
        for pid in [*(process.pid for process in processes), child_pid]:
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for process in processes:
            process.wait()
