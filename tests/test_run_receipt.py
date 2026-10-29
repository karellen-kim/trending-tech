"""배치 경계와 실제 게시 결과를 외부 호출 없이 검증한다."""
import json
from unittest.mock import Mock

import pytest

import main
import summarizer


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv('RUN_DATE', '2026-10-29')
    monkeypatch.delenv('DRY', raising=False)
    monkeypatch.setattr(main, 'LOGS_DIR', tmp_path / 'logs', raising=False)
    monkeypatch.setattr(main, 'DOCS_DIR', tmp_path / 'docs')
    data = {'date': '2026-10-29', 'github': [], 'company_blogs': [], 'dev_blogs': [],
            'papers': [], 'hn': [], 'reddit': [], 'source_status': {
                'hn': {'required': False, 'status': 'success', 'count': 0},
                'reddit': {'required': False, 'status': 'success', 'count': 0}}}
    monkeypatch.setattr(main, 'collect', Mock(return_value=data))
    monkeypatch.setattr(main, 'summarize', lambda value: value)
    monkeypatch.setattr(main, 'make_audio', lambda value: '')
    monkeypatch.setattr(main, 'save_weekly_page', lambda day: None)
    monkeypatch.setattr(main, 'save_monthly_page', lambda day: '')
    monkeypatch.setattr(main, 'git_commit_push', Mock(return_value={'status': 'success', 'commit_sha': 'a' * 40}))
    monkeypatch.setattr(main, 'send_slack', Mock(return_value={'status': 'success', 'http_status': 200}))
    monkeypatch.setattr(main.signal, 'alarm', Mock(return_value=0))
    return data, tmp_path


def receipt(tmp_path):
    paths = list((tmp_path / 'logs' / 'runs').glob('*.json'))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_published_requires_artifacts_and_both_publications(pipeline):
    _, tmp_path = pipeline
    main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'published'
    assert state['exit_code'] == 0
    assert state['started_at'] and state['finished_at'] and state['run_id']
    assert state['stages']['artifacts']['status'] == 'success'
    assert state['stages']['git']['commit_sha'] == 'a' * 40
    assert state['stages']['slack']['http_status'] == 200


@pytest.mark.parametrize('error, status, code', [
    (RuntimeError('secret must not appear'), 'failed', 1),
    (SystemExit(143), 'interrupted', 143),
    (KeyboardInterrupt(), 'interrupted', 130),
])
def test_errors_preserve_exit_evidence_and_block_publication(pipeline, monkeypatch, error, status, code):
    _, tmp_path = pipeline
    monkeypatch.setattr(main, 'summarize', Mock(side_effect=error))
    with pytest.raises(type(error)):
        main.main()
    state = receipt(tmp_path)
    assert state['status'] == status
    assert state['exit_code'] == code
    assert 'secret must not appear' not in json.dumps(state)
    main.git_commit_push.assert_not_called()
    main.send_slack.assert_not_called()


def test_git_failure_blocks_slack(pipeline, monkeypatch):
    _, tmp_path = pipeline
    monkeypatch.setattr(main, 'git_commit_push', Mock(side_effect=RuntimeError('git failed')))
    with pytest.raises(RuntimeError):
        main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'failed'
    assert state['stages']['git']['status'] == 'failed'
    main.send_slack.assert_not_called()


def test_slack_failure_preserves_git_success(pipeline, monkeypatch):
    _, tmp_path = pipeline
    monkeypatch.setattr(main, 'send_slack', Mock(side_effect=RuntimeError('slack failed')))
    with pytest.raises(RuntimeError):
        main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'failed'
    assert state['stages']['git']['status'] == 'success'
    assert state['stages']['slack']['status'] == 'failed'


def test_dry_is_never_published(pipeline, monkeypatch):
    _, tmp_path = pipeline
    monkeypatch.setenv('DRY', '1')
    main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'dry_run'
    assert state['stages']['git']['status'] == 'skipped'
    assert state['stages']['slack']['status'] == 'skipped'
    main.git_commit_push.assert_not_called()
    main.send_slack.assert_not_called()


def test_optional_source_failure_is_partial(pipeline):
    data, tmp_path = pipeline
    data['source_status']['reddit']['status'] = 'failed'
    main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'partial'
    saved = json.loads((tmp_path / 'docs' / '2026-10-29.json').read_text())
    assert saved['source_status']['reddit']['status'] == 'failed'


def test_pending_llm_prevents_publication(pipeline, monkeypatch):
    _, tmp_path = pipeline
    def unfinished(data):
        summarizer._log_llm_event('llm_call_started', call_id='unfinished', context='test')
        return data
    monkeypatch.setattr(main, 'summarize', unfinished)
    with pytest.raises(RuntimeError, match='LLM'):
        main.main()
    state = receipt(tmp_path)
    assert state['status'] == 'failed'
    assert state['llm_calls']['unfinished'] == 'running'
    main.git_commit_push.assert_not_called()


def test_llm_finish_is_linked_to_run(pipeline, monkeypatch):
    _, tmp_path = pipeline
    def finished(data):
        summarizer._log_llm_event('llm_call_started', call_id='finished', context='test')
        summarizer._log_llm_event('llm_call_finished', call_id='finished', status='success')
        return data
    monkeypatch.setattr(main, 'summarize', finished)
    main.main()
    state = receipt(tmp_path)
    assert state['llm_calls'] == {'finished': 'success'}
    events = [json.loads(line) for line in (tmp_path / 'logs' / 'llm-calls.log').read_text().splitlines()]
    assert all(event['run_id'] == state['run_id'] for event in events)


def test_missing_slack_configuration_is_partial(pipeline, monkeypatch):
    _, tmp_path = pipeline
    monkeypatch.setattr(main, 'send_slack', Mock(return_value={'status': 'skipped', 'reason': 'not_configured'}))
    main.main()
    assert receipt(tmp_path)['status'] == 'partial'


def test_missing_artifact_blocks_publication(pipeline, monkeypatch):
    _, tmp_path = pipeline
    monkeypatch.setattr(main, 'save_html', lambda value: [])
    with pytest.raises(FileNotFoundError):
        main.main()
    assert receipt(tmp_path)['stages']['artifacts']['status'] == 'failed'
    main.git_commit_push.assert_not_called()


def test_push_failure_preserves_commit_evidence(pipeline, monkeypatch):
    import subprocess
    _, tmp_path = pipeline
    def git(args, **kwargs):
        if args[1] == 'push':
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout='b' * 40)
    # Use the real publication function, with every git subprocess mocked.
    monkeypatch.setattr(main, 'git_commit_push', _real_git_commit_push)
    monkeypatch.setattr(main.subprocess, 'run', git)
    with pytest.raises(subprocess.CalledProcessError):
        main.main()
    state = receipt(tmp_path)
    assert state['stages']['git'] == {'status': 'failed', 'commit_sha': 'b' * 40,
                                      'committed': True, 'pushed': False}
    main.send_slack.assert_not_called()


_real_git_commit_push = main.git_commit_push


def test_concurrent_llm_events_preserve_ids_and_terminal_failure(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import run_receipt
    with pytest.raises(RuntimeError):
        with run_receipt.RunReceipt(tmp_path, '2026-10-29') as run:
            def events(index):
                fields = {'call_id': str(index), 'status': 'success'}
                run_receipt.record_llm_event('llm_call_started', fields)
                run_receipt.record_llm_event('llm_call_finished', fields)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(events, range(12)))
            assert run.state['llm_calls'] == {str(i): 'success' for i in range(12)}
            raise RuntimeError('failed')
    saved = json.loads(run.path.read_text())
    assert saved['status'] == 'failed'
    assert saved['llm_calls'] == {str(i): 'success' for i in range(12)}
    run_receipt.record_llm_event('llm_call_finished', {'call_id': 'late', 'status': 'success'})
    assert json.loads(run.path.read_text()) == saved


def test_atomic_replace_failure_preserves_previous_receipt(tmp_path, monkeypatch):
    import run_receipt
    run = run_receipt.RunReceipt(tmp_path, '2026-10-29')
    run.persist()
    before = run.path.read_bytes()
    monkeypatch.setattr(run_receipt.os, 'replace', Mock(side_effect=OSError('disk failure')))
    run.state['status'] = 'failed'
    with pytest.raises(OSError):
        run.persist()
    assert run.path.read_bytes() == before
    assert list(tmp_path.glob('.run-*')) == []


@pytest.mark.parametrize('signum, expected_code, expected_status', [
    (15, 143, 'interrupted'), (9, -9, 'running'), (14, 1, 'interrupted')])
def test_real_process_interruption_leaves_honest_receipt(tmp_path, signum, expected_code, expected_status):
    import os
    import selectors
    import subprocess
    import sys
    from pathlib import Path
    # The child replaces collection with an idle loop before any external work.
    script = '''
import main, signal, sys
from pathlib import Path
main.LOGS_DIR = Path(sys.argv[1])
def collect(*args, **kwargs):
    print('TEST_READY', flush=True)
    while True:
        signal.pause()
main.collect = collect
main.main()
'''
    process = subprocess.Popen([sys.executable, '-c', script, str(tmp_path)],
                               cwd=Path(main.__file__).parent, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               env=dict(os.environ, RUN_DATE='2026-10-29', PYTHONDONTWRITEBYTECODE='1'))
    try:
        # Read pipe bytes to avoid TextIO buffering hiding the readiness line.
        output = b''
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b'TEST_READY\n' not in output:
                assert selector.select(timeout=10), 'child did not reach isolated collection'
                chunk = os.read(process.stdout.fileno(), 4096)
                assert chunk, 'child exited before isolated collection'
                output += chunk
        os.kill(process.pid, signum)
        process.communicate(timeout=10)
        assert process.returncode == expected_code
        state = receipt_for_directory(tmp_path / 'runs')
        assert state['status'] == expected_status
        assert state['exit_code'] == (None if signum == 9 else expected_code)
        assert state['stages']['git']['status'] == 'not_started'
        if signum == 9:
            assert state['finished_at'] is None
        else:
            assert state['finished_at'] is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def receipt_for_directory(directory):
    paths = list(directory.glob('*.json'))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())
