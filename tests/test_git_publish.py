"""Exercise publication against synthetic local remotes, never GitHub."""
import subprocess
import os

import pytest

import main


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          capture_output=True, text=True)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)],
                   check=True, capture_output=True)
    local = tmp_path / 'local'
    subprocess.run(['git', 'clone', str(remote), str(local)], check=True, capture_output=True)
    git(local, 'config', 'user.email', 'test@example.com')
    git(local, 'config', 'user.name', 'Test')
    docs = local / 'docs'
    docs.mkdir()
    for name in ('2026-11-03.html', '2026-11-03.json', '2026-W45.html',
                 '2026-W45.json', 'index.html'):
        (docs / name).write_text('base\n')
    git(local, 'add', '.')
    git(local, 'commit', '-m', 'base')
    git(local, 'push', '-u', 'origin', 'HEAD')
    other = tmp_path / 'other'
    subprocess.run(['git', 'clone', str(remote), str(other)], check=True, capture_output=True)
    git(other, 'config', 'user.email', 'test@example.com')
    git(other, 'config', 'user.name', 'Test')
    monkeypatch.chdir(local)
    return local, other, remote


def advance(other, conflict=False):
    path = other / ('docs/index.html' if conflict else 'remote.txt')
    path.write_text('remote change\n')
    git(other, 'add', '.')
    git(other, 'commit', '-m', 'remote advance')
    git(other, 'push')


@pytest.mark.parametrize('remote_advance', [False, True])
def test_publish_preserves_remote_changes(repos, remote_advance):
    local, other, remote = repos
    if remote_advance:
        advance(other)
    (local / 'docs/index.html').write_text('daily change\n')
    result = main.git_commit_push('2026-11-03')
    assert result['pushed'] is True
    assert result['commit_sha'] == git(remote, 'rev-parse', 'HEAD').stdout.strip()
    assert git(remote, 'show', 'HEAD:docs/index.html').stdout == 'daily change\n'
    if remote_advance:
        assert git(remote, 'show', 'HEAD:remote.txt').stdout == 'remote change\n'


def test_conflict_preserves_commit_and_aborts_rebase(repos):
    local, other, remote = repos
    advance(other, conflict=True)
    before = git(remote, 'rev-parse', 'HEAD').stdout
    (local / 'docs/index.html').write_text('daily change\n')
    with pytest.raises(subprocess.CalledProcessError):
        main.git_commit_push('2026-11-03')
    assert git(local, 'show', 'HEAD:docs/index.html').stdout == 'daily change\n'
    assert git(local, 'status', '--porcelain').stdout == ''
    assert not (local / '.git/rebase-merge').exists()
    assert git(remote, 'rev-parse', 'HEAD').stdout == before


def test_retry_failure_records_rebased_sha_and_stops(repos, monkeypatch):
    local, other, remote = repos
    advance(other)
    (local / 'docs/index.html').write_text('daily change\n')
    run = subprocess.run
    pushes = []
    stages = []

    def reject_retry(args, **kwargs):
        if args[:2] == ['git', 'push']:
            pushes.append(args)
            if len(pushes) == 2:
                raise subprocess.CalledProcessError(1, args)
        return run(args, **kwargs)

    monkeypatch.setattr(main.subprocess, 'run', reject_retry)
    monkeypatch.setattr(main, 'record_stage', lambda *args, **kwargs: stages.append(kwargs))
    with pytest.raises(subprocess.CalledProcessError):
        main.git_commit_push('2026-11-03')
    assert len(pushes) == 2
    assert stages[0]['commit_sha'] != stages[1]['commit_sha']
    assert stages[1]['commit_sha'] == git(local, 'rev-parse', 'HEAD').stdout.strip()
    assert stages[1]['pushed'] is False
    assert git(remote, 'show', 'HEAD:docs/index.html').stdout == 'base\n'


def test_dirty_work_is_preserved_without_recovery(repos):
    local, other, remote = repos
    (local / 'tracked.txt').write_text('base\n')
    git(local, 'add', 'tracked.txt')
    git(local, 'commit', '-m', 'tracked work')
    advance(other)
    (local / 'docs/index.html').write_text('daily change\n')
    (local / 'tracked.txt').write_text('keep me\n')
    before = git(remote, 'rev-parse', 'HEAD').stdout
    with pytest.raises(RuntimeError, match='clean working tree'):
        main.git_commit_push('2026-11-03')
    assert (local / 'tracked.txt').read_text() == 'keep me\n'
    assert git(remote, 'rev-parse', 'HEAD').stdout == before


def test_unrelated_untracked_work_is_preserved_during_recovery(repos):
    local, other, remote = repos
    advance(other)
    (local / 'docs/index.html').write_text('daily change\n')
    (local / 'untracked.txt').write_text('keep me\n')
    result = main.git_commit_push('2026-11-03')
    assert result['pushed'] is True
    assert result['commit_sha'] == git(remote, 'rev-parse', 'HEAD').stdout.strip()
    assert (local / 'untracked.txt').read_text() == 'keep me\n'
    assert git(remote, 'show', 'HEAD:remote.txt').stdout == 'remote change\n'
    assert git(remote, 'ls-tree', 'HEAD', 'untracked.txt').stdout == ''


def test_untracked_collision_is_preserved_without_publishing(repos):
    local, other, remote = repos
    advance(other)
    before = git(remote, 'rev-parse', 'HEAD').stdout
    (local / 'docs/index.html').write_text('daily change\n')
    (local / 'remote.txt').write_text('keep me\n')
    with pytest.raises(subprocess.CalledProcessError):
        main.git_commit_push('2026-11-03')
    assert (local / 'remote.txt').read_text() == 'keep me\n'
    assert git(local, 'show', 'HEAD:docs/index.html').stdout == 'daily change\n'
    assert not (local / '.git/rebase-merge').exists()
    assert git(remote, 'rev-parse', 'HEAD').stdout == before


def test_general_push_failure_is_not_retried(repos, monkeypatch):
    local, _, _ = repos
    (local / 'docs/index.html').write_text('daily change\n')
    run = subprocess.run
    pushes = []

    def fail(args, **kwargs):
        if args[:2] == ['git', 'push']:
            pushes.append(args)
            raise subprocess.CalledProcessError(128, args, stderr='authentication failed')
        assert args[:2] != ['git', 'pull']
        return run(args, **kwargs)

    monkeypatch.setattr(main.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        main.git_commit_push('2026-11-03')
    assert len(pushes) == 1
