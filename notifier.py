import requests

def send_slack(webhook_url: str, date: str, highlights: list[str]) -> None:
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL 미설정, 전송 건너뜀")
        return
    hl_text = "\n".join(f"• {h}" for h in highlights[:5])
    text = f"*{date} 개발 트렌드*\n{hl_text}\nhttps://karellen-kim.github.io/trending-tech/{date}.html"
    resp = requests.post(webhook_url, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"[Slack] 전송 실패: {resp.status_code} {resp.text}")
