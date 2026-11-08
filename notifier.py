import math
import time

import requests

from run_receipt import record_stage

PAGE_URL = "https://karellen-kim.github.io/trending-tech"


def _build_text(date: str, take: dict | None, highlights: list[str]) -> str:
    """해석이 있으면 해석을 보내고, 없으면 기존처럼 목록을 보낸다."""
    link = f"{PAGE_URL}/{date}.html"
    if take and take.get("headline"):
        parts = [f"*{date} 개발 트렌드*", "", f"*{take['headline']}*"]
        if take.get("body"):
            parts += ["", take["body"]]
        refs = take.get("refs") or []
        if refs:
            parts += [""] + [f"• <{r['url']}|{r['text']}>" if r.get("url")
                             else f"• {r['text']}" for r in refs[:5]]
        parts += ["", link]
        return "\n".join(parts)

    hl_text = "\n".join(f"• {h}" for h in highlights[:5])
    return f"*{date} 개발 트렌드*\n{hl_text}\n{link}"


def send_slack(webhook_url: str, date: str, highlights: list[str],
               take: dict | None = None) -> dict:
    """Slack 수신 확인을 반환하고 HTTP 실패는 본문·webhook 없이 전파한다."""
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL 미설정, 전송 건너뜀")
        return {"status": "skipped", "reason": "not_configured"}
    text = _build_text(date, take, highlights)
    waited = 0
    for attempt in range(1, 4):
        evidence = {"attempts": attempt, "retry_wait_seconds": waited}
        delay = 2 ** (attempt - 1)
        try:
            resp = requests.post(webhook_url, json={"text": text}, timeout=10)
        except requests.RequestException as error:
            kind = next((label for cls, label in (
                (requests.ConnectTimeout, "connect_timeout"),
                (requests.ReadTimeout, "read_timeout"),
                (requests.exceptions.SSLError, "tls_error"),
                (requests.ConnectionError, "connection_error")) if isinstance(error, cls)), "request_error")
            retry = kind == "connect_timeout"
            evidence.update(error_kind=kind, delivery_state="not_sent" if retry else "unknown")
            message = "Slack request failed"
        else:
            if resp.status_code == 200:
                return {"status": "success", "http_status": resp.status_code,
                        "delivery_state": "acknowledged", **evidence}
            retry = resp.status_code == 429
            evidence.update(error_kind="rate_limited" if retry else "http_error",
                            delivery_state="unknown" if resp.status_code >= 500 else "rejected",
                            http_status=resp.status_code)
            message = f"Slack HTTP {resp.status_code}"
            if retry:
                try:
                    value = float(resp.headers.get("Retry-After", ""))
                    if math.isfinite(value) and value >= 0:
                        delay = value
                except (TypeError, ValueError):
                    pass
        # Only a pre-send timeout or explicit rejection makes POST replay safe.
        if not retry or attempt == 3 or waited + delay > 30:
            record_stage("slack", "failed", **evidence)
            raise RuntimeError(message) from None
        record_stage("slack", "running", **evidence)
        time.sleep(delay)
        waited += delay
