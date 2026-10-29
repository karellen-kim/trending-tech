import requests

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
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=10)
    except requests.RequestException:
        raise RuntimeError("Slack request failed") from None
    if resp.status_code != 200:
        raise RuntimeError(f"Slack HTTP {resp.status_code}")
    return {"status": "success", "http_status": resp.status_code}
