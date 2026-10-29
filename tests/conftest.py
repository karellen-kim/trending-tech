"""테스트의 LLM 진단 기록이 운영 로그에 섞이지 않게 격리한다."""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_diagnostics(monkeypatch, tmp_path):
    """실패 주입 테스트도 호출 로그를 테스트 임시 디렉터리에만 남긴다."""
    monkeypatch.setattr('summarizer.LOGS_DIR', tmp_path / 'logs')


@pytest.fixture(autouse=True)
def isolate_run_receipts(monkeypatch, tmp_path):
    """배치 테스트의 영수증은 운영 로그에 쓰지 않는다."""
    monkeypatch.setattr('main.LOGS_DIR', tmp_path / 'logs', raising=False)


@pytest.fixture(autouse=True)
def deny_live_http(monkeypatch):
    """테스트에서 모의 처리하지 않은 HTTP 요청은 즉시 차단한다."""
    def denied(*args, **kwargs):
        raise AssertionError('Live HTTP is forbidden in tests')
    monkeypatch.setattr('requests.sessions.Session.request', denied)
