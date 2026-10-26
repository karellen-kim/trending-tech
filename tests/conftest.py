"""테스트의 LLM 진단 기록이 운영 로그에 섞이지 않게 격리한다."""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_diagnostics(monkeypatch, tmp_path):
    """실패 주입 테스트도 호출 로그를 테스트 임시 디렉터리에만 남긴다."""
    monkeypatch.setattr('summarizer.LOGS_DIR', tmp_path / 'logs')
