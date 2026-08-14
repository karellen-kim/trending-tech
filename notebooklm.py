"""NotebookLM 오디오 리뷰 생성 클라이언트.

notebooklm-podcast-automator(FastAPI + Playwright)를 별도 프로세스로 띄워두고
그 REST API 를 호출한다. 준비 절차는 docs/notebooklm-setup.md 참고.

NotebookLM 은 부가 기능이므로 어떤 실패도 배치 전체를 멈추지 않는다 — 항상 None 을 돌려준다.
"""
import time

import requests

from config import (NOTEBOOKLM_API_URL, NOTEBOOKLM_STYLE, NOTEBOOKLM_LANGUAGE,
                    NOTEBOOKLM_TIMEOUT, NOTEBOOKLM_POLL_INTERVAL)

_HTTP_TIMEOUT = 60


def _post(path: str, payload: dict | None = None) -> dict:
    resp = requests.post(f"{NOTEBOOKLM_API_URL}{path}", json=payload, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _get(path: str) -> dict:
    resp = requests.get(f"{NOTEBOOKLM_API_URL}{path}", timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def generate_audio_review(urls: list[str], out_path: str, title: str = "",
                          timeout: int = NOTEBOOKLM_TIMEOUT) -> str | None:
    """링크를 노트북에 올리고 오디오 오버뷰를 만들어 내려받는다. 실패하면 None."""
    urls = [u for u in urls if u]
    if not urls:
        return None
    try:
        # 노트북 하나를 재사용하므로 지난 소스를 먼저 비운다
        _post("/sources/clear")

        uploaded = _post("/sources/upload",
                         {"sources": [{"type": "url", "content": u} for u in urls]})
        if not uploaded.get("overall_success"):
            failed = [r for r in uploaded.get("results", []) if not r.get("success")]
            print(f"[NotebookLM] 소스 업로드 일부 실패: {len(failed)}건")

        payload = {"style": NOTEBOOKLM_STYLE, "language": NOTEBOOKLM_LANGUAGE}
        if title:
            payload["prompt"] = (f"{title}의 주요 기술 소식이야. 각 글의 핵심이 무엇인지, "
                                 f"서로 어떤 흐름으로 이어지는지 짚어줘.")
        job = _post("/audio/generate", payload)
        job_id = job.get("job_id")
        if not job_id:
            print("[NotebookLM] job_id 를 받지 못했다")
            return None

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = _get(f"/audio/status/{job_id}")
            status = str(state.get("status", "")).lower()
            if status == "completed":
                break
            if status == "failed":
                print(f"[NotebookLM] 생성 실패: {state.get('error', '')}")
                return None
            time.sleep(NOTEBOOKLM_POLL_INTERVAL)
        else:
            print(f"[NotebookLM] 타임아웃({timeout}s)")
            return None

        resp = requests.get(f"{NOTEBOOKLM_API_URL}/audio/download/{job_id}", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"[NotebookLM] 오디오 저장: {out_path}")
        return out_path
    except Exception as e:
        print(f"[NotebookLM] 실패: {type(e).__name__}: {str(e)[:150]}")
        return None
