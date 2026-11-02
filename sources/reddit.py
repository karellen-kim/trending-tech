from time import sleep
from collections import deque
import fcntl
import json
import math
import os
from tempfile import NamedTemporaryFile

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from config import now_kst, LOGS_DIR
from config import REDDIT_SUBREDDITS, MAX_REDDIT_ITEMS

_HEADERS = {"User-Agent": "trending-tech-bot/1.0"}
KST = timezone(timedelta(hours=9))
MAX_ATTEMPTS = 3
MAX_RETRY_WAIT = 30
STATE_DIR = LOGS_DIR / "reddit"


def _utc_now() -> datetime:
    """HTTP 날짜 형태의 Retry-After를 계산할 UTC 시각을 제공한다."""
    return datetime.now(timezone.utc)


def _retry_delay(value: str | None, attempt: int) -> float:
    """유효한 서버 대기를 우선하고 없거나 잘못된 헤더에는 제한된 backoff를 쓴다."""
    if value:
        if value.strip().isascii() and value.strip().isdigit():
            return int(value.strip())
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, (retry_at - _utc_now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return 2 ** attempt

def _today_cutoff() -> datetime:
    n = now_kst()
    return n.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

def fetch_subreddit(name: str, max_items: int = MAX_REDDIT_ITEMS) -> list[dict]:
    """오늘 Reddit RSS에서 본문을 보존하고 요청 실패는 호출자에게 전달한다."""
    url = f"https://www.reddit.com/r/{name}/top.rss?t=day"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.version or (feed.bozo and not feed.entries):
        raise ValueError("Invalid Reddit feed")
    cutoff = _today_cutoff()
    items = []
    for entry in feed.entries:
        pub = getattr(entry, "published_parsed", None)
        if pub:
            try:
                if datetime(*pub[:6], tzinfo=timezone.utc) < cutoff:
                    continue
            except Exception:
                pass
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        # RSS의 작성자·[link]·[comments] 메타데이터는 본문이 아니다.
        candidates = [part.get("value", "") for part in entry.get("content", [])]
        candidates.append(entry.get("summary", ""))
        bodies = []
        for html in candidates:
            soup = BeautifulSoup(html or "", "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            bodies.append(" ".join(body.get_text(" ", strip=True) for body in soup.select(".md")))
        content = max(bodies, key=len, default="")
        items.append({
            "title": title,
            "url": link,
            "source": f"r/{name}",
            "summary": "",
            "content": content,
        })
        if len(items) >= max_items:
            break
    return items

def _save_limit(state: dict) -> None:
    """잠금을 보유한 프로세스가 다음 허용 시각을 원자 저장한다."""
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=STATE_DIR,
                                prefix=".state-", delete=False) as stream:
            temporary = stream.name
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, STATE_DIR / "state.json")
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _load_limit() -> dict:
    """손상된 공유 상태를 초기화해 제한을 우회하지 않는다."""
    try:
        state = json.loads((STATE_DIR / "state.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"next_allowed_at": 0, "retry_pending": False}
    if (not isinstance(state, dict)
            or type(state.get("next_allowed_at")) not in (int, float)
            or not math.isfinite(state["next_allowed_at"])
            or state["next_allowed_at"] < 0
            or type(state.get("retry_pending")) is not bool):
        raise ValueError("Invalid Reddit cooldown state")
    return state


def _limit_headers(response) -> dict:
    """RSS 제한 기준을 추정하지 않고 숫자인 진단 헤더만 보존한다."""
    headers = {}
    if response is not None:
        for name in ("x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-used"):
            try:
                value = float(response.headers.get(name, ""))
                if math.isfinite(value) and value >= 0:
                    headers[name] = value
            except (TypeError, ValueError, OverflowError):
                pass
    return headers


def _collect_locked(sources: list[dict], all_items: list[dict]) -> None:
    """첫 시도를 우선하며 전체 요청·대기 예산과 공유 cooldown을 지킨다."""
    state = _load_limit()
    pending = deque(range(len(sources)))
    waited = 0
    requests_left = len(sources) + MAX_ATTEMPTS - 1
    delay_owner = None
    stop_reason = "request_budget_exhausted"
    while pending and requests_left:
        index = pending[0]
        result = sources[index]
        delay = max(0, state["next_allowed_at"] - _utc_now().timestamp())
        if state["retry_pending"] and waited + delay > MAX_RETRY_WAIT:
            stop_reason = "wait_budget_exceeded"
            break
        if delay:
            sleep(delay)
            if state["retry_pending"]:
                waited += delay
                owner = delay_owner if delay_owner is not None else result
                owner["retry_wait_seconds"] += delay
        pending.popleft()
        result["attempts"] += 1
        requests_left -= 1
        evidence = {"requested_at": _utc_now().isoformat(), "in_flight": 1}
        result["requests"].append(evidence)
        try:
            items = fetch_subreddit(REDDIT_SUBREDDITS[index])
            all_items.extend(items)
            result.update(status="success", count=len(items), http_status=200)
            result.pop("error_type", None)
            result.pop("reason", None)
            evidence["http_status"] = 200
            state = {"next_allowed_at": _utc_now().timestamp() + 1, "retry_pending": False}
            delay_owner = None
        except Exception as error:
            response = getattr(error, "response", None)
            code = response.status_code if response is not None else None
            result.update(http_status=code, error_type=type(error).__name__)
            evidence.update(http_status=code, rate_limit_headers=_limit_headers(response))
            state = {"next_allowed_at": _utc_now().timestamp() + 1, "retry_pending": False}
            delay_owner = None
            if code == 429:
                delay = _retry_delay(response.headers.get("Retry-After"), result["attempts"])
                result["retry_after_seconds"] = delay
                evidence["retry_after_seconds"] = delay
                # 한 소스의 제한 범위는 불명확하므로 다른 소스도 서버 대기를 지킨다.
                state = {"next_allowed_at": _utc_now().timestamp() + max(1, delay),
                         "retry_pending": True}
                delay_owner = result
                if result["attempts"] < MAX_ATTEMPTS:
                    pending.append(index)
                else:
                    result["reason"] = "retries_exhausted"
        _save_limit(state)
    for index in pending:
        result = sources[index]
        result["reason"] = stop_reason
        result["next_allowed_at"] = state["next_allowed_at"]
        if not result["attempts"]:
            result["status"] = "skipped_rate_limit"


def fetch_all_reddit() -> dict:
    """동일 checkout의 수집을 직렬화하고 소스별 누락·제한 증거를 반환한다."""
    all_items = []
    sources = [{"name": f"r/{name}", "status": "failed", "count": 0, "attempts": 0,
                "retry_wait_seconds": 0, "requests": []} for name in REDDIT_SUBREDDITS]
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with (STATE_DIR / "collection.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                for result in sources:
                    result.update(status="skipped_rate_limit", reason="collection_in_progress")
            else:
                try:
                    _collect_locked(sources, all_items)
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
    except (OSError, ValueError, TypeError, OverflowError) as error:
        affected = [result for result in sources if result["status"] != "success"]
        # 마지막 성공 뒤 상태 저장·잠금 해제가 실패해도 장애를 숨기지 않는다.
        for result in affected or sources[-1:]:
            result.update(status="failed", reason="coordination_unavailable",
                          error_type=type(error).__name__)
    for result in sources:
        print(f"[Reddit] {result['name']} {result['status']} count={result['count']} attempts={result['attempts']}")
    successes = sum(result["status"] == "success" for result in sources)
    status = "success" if successes == len(sources) else ("partial" if successes else "failed")
    return {"items": all_items, "sources": sources, "status": status}
