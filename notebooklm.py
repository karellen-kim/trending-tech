"""Gemini Notebook(구 NotebookLM)에 링크를 올리고 AI 오디오 오버뷰 생성을 시킨다.

2026-08 기준 실제 UI 를 브라우저로 확인해 만든 셀렉터다.
  notebooklm.google.com -> notebook.google.com 으로 리다이렉트되고
  제품명도 "NotebookLM" -> "Gemini Notebook" 으로 바뀌었다.

오디오 파일은 내려받지 않는다. 재생은 Gemini Notebook 에서 직접 한다.
부가 기능이므로 어떤 실패도 배치를 멈추지 않는다 — 항상 bool 을 돌려준다.

로그인 세션은 NOTEBOOKLM_PROFILE_DIR 의 Chrome 프로필에 저장된다.
최초 1회는 `python -m notebooklm login` 으로 창을 띄워 직접 로그인해야 한다.
"""
import sys
import json
import re

from config import (LOGS_DIR, NOTEBOOKLM_PROFILE_DIR, NOTEBOOKLM_FORMAT,
                    NOTEBOOKLM_LANGUAGE, NOTEBOOKLM_HEADLESS, NOTEBOOKLM_TIMEOUT)

# 실제 화면에서 확인한 라벨. UI 언어가 영어일 수도 있어 둘 다 받는다.
_L = {
    "add_source": ["출처 추가", "소스 추가", "Add source", "Add sources"],
    "website": ["웹사이트", "Website"],
    "url_box": ["링크를 붙여넣으세요.", "Paste URLs"],
    "insert": ["삽입", "Insert"],
    "audio_overview": ["AI 오디오 오버뷰", "Audio Overview"],
    "generate": ["생성", "Generate"],
    "generating": ["생성 중", "Generating"],
    "create_notebook": ["새 노트북", "새로 만들기", "새 노트 만들기", "Create new", "New notebook"],
    "close_dialog": ["대화상자 닫기", "Close dialog"],   # 영어 라벨은 화면에서 확인 못 함
}
_FORMATS = {
    "deep_dive": ["심층 분석", "Deep Dive"],
    "summary": ["요약", "Summary"],
    "criticism": ["비평", "Critique"],
    "debate": ["토론", "Debate"],
}
_STEP_TIMEOUT = 30_000   # 개별 UI 조작 대기(ms)


def _click_any(page, labels, timeout=_STEP_TIMEOUT, exact=False) -> bool:
    """여러 후보 라벨 중 먼저 보이는 것을 클릭한다.

    exact=True 면 role=button 정확 매칭을 가장 먼저 시도한다. '생성'처럼 짧은 라벨은
    exact=False 매칭에서 화면에 없는 다른 요소의 접근성 이름에 부분 포함돼, 그 엉뚱한
    요소가 보이길 기다리다 타임아웃되는 경우가 있었다 (2026-10 실측: 오디오 오버뷰
    생성 모달의 '생성' 버튼 — 모달 밖 다른 요소와 섞여 클릭이 통째로 실패했다)."""
    deadline = timeout
    for label in labels:
        targets = []
        if exact:
            targets.append(page.get_by_role("button", name=label, exact=True))
        targets += [page.get_by_role("button", name=label, exact=False),
                    page.get_by_text(label, exact=False)]
        for target in targets:
            try:
                el = target.first
                el.wait_for(state="visible", timeout=deadline // max(len(labels), 1))
                el.click()
                return True
            except Exception:
                continue
    return False


TITLE_MAX = 80


def _notebook_title(date_str: str, headline: str = "") -> str:
    """[Daily] YY.MM.DD 제목 — 노트북 목록에서 날짜별로 구분되도록 붙인다."""
    head = " ".join(str(headline or "").split())
    base = f"[Daily] {date_str}"
    if not head:
        return base
    room = TITLE_MAX - len(base) - 1
    if len(head) > room:
        head = head[:room - 1] + "…"
    return f"{base} {head}"


def _set_title(page, title: str, retries: int = 2) -> bool:
    """노트북 제목을 바꾼다. 제목 입력란은 페이지의 첫 번째 textbox 다.

    소스를 추가하면 Gemini 가 내용을 보고 제목을 자동 생성해 덮어쓴다.
    (실측: "[Daily] 26.08.17 ..." -> "Cloudflare and AWS AgentCore Monitoring ...")
    그래서 모든 작업이 끝난 뒤에 설정하고, 실제로 반영됐는지 값을 읽어 확인한다."""
    if not title:
        return False
    for attempt in range(retries):
        try:
            box = page.get_by_role("textbox").first
            box.click()
            box.fill(title)
            page.keyboard.press("Tab")   # 포커스를 빼야 저장된다
            page.wait_for_timeout(1_500)
            if box.input_value().strip() == title.strip():
                return True
        except Exception as e:
            print(f"[Notebook] 제목 설정 실패({attempt + 1}/{retries}): {type(e).__name__}")
        page.wait_for_timeout(2_000)
    print("[Notebook] 제목이 반영되지 않았다 (자동 제목에 덮어쓰였을 수 있음)")
    return False


def _create_notebook(page, timeout_ms: int) -> str:
    """홈에서 새 노트북을 만들고 그 URL 을 돌려준다. 실패하면 빈 문자열."""
    page.goto("https://notebook.google.com/", wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(6_000)
    if not _click_any(page, _L["create_notebook"]):
        print("[Notebook] '새로 만들기' 버튼을 찾지 못했다")
        return ""
    page.wait_for_timeout(6_000)
    url = page.url.split("?")[0]
    return url if "/notebook/" in url else ""


def _visible_any(page, labels, timeout=3_000) -> bool:
    """후보 라벨 중 하나라도 화면에 보이는지 확인한다."""
    for label in labels:
        for target in (page.get_by_role("button", name=label, exact=False),
                       page.get_by_text(label, exact=False)):
            try:
                target.first.wait_for(state="visible", timeout=timeout)
                return True
            except Exception:
                continue
    return False


def _dismiss_dialogs(page) -> None:
    """공지 모달이 떠 있으면 닫는다.
    2026-09-11 배치부터 새 노트북 위에 '5시간마다 한도 초기화' 안내 모달이 뜬다.
    모달이 클릭을 가로채 '웹사이트' 가 보이는데도 누르지 못하고 실패했다.
    소스 다이얼로그에도 '닫기' 버튼이 있어 이름을 정확히 맞춘다."""
    for label in _L["close_dialog"]:
        try:
            btn = page.get_by_role("button", name=label, exact=True).first
            btn.wait_for(state="visible", timeout=2_000)
            btn.click()
            page.wait_for_timeout(1_000)
        except Exception:
            continue


def _click_source_button(page, labels) -> bool:
    """배경 설명의 같은 문구가 아니라 실제 소스 버튼만 누른다."""
    for label in labels:
        try:
            button = page.get_by_role("button", name=label, exact=False).first
            button.wait_for(state="visible", timeout=2_000)
            button.click()
            return True
        except Exception:
            continue
    return False


def _open_source_dialog(page) -> bool:
    """이미 열린 URL 입력 화면을 보존하고 실제 소스 버튼으로 진입한다."""
    for placeholder in _L["url_box"]:
        try:
            if page.get_by_placeholder(placeholder, exact=False).first.is_visible():
                return True
        except Exception:
            continue
    if _click_source_button(page, _L["website"]):
        return True
    _dismiss_dialogs(page)
    if not _click_source_button(page, _L["add_source"]):
        return False
    page.wait_for_timeout(1_500)
    return _click_source_button(page, _L["website"])


def _wait_studio_ready(page, timeout_ms: int = 25_000, step_ms: int = 1_000) -> None:
    """소스 크롤링이 끝나 스튜디오 버튼(AI 오디오 오버뷰 등)이 활성화될 때까지 기다린다.

    2026-10 실측: 크롤링이 안 끝난 버튼은 class 에 'disabled-tile' 이 붙어 있는데,
    DOM disabled 속성은 없어서 Playwright 클릭은 '성공'으로 판정되고도 생성 다이얼로그가
    열리지 않는다. 고정 대기(8초)만으로는 간헐적으로 부족해서 class 가 빠질 때까지 폴링한다.
    버튼을 못 찾거나 타임아웃까지 안 빠져도 예외 없이 조용히 리턴한다 — 그 뒤 _click_any 가
    통상적인 실패 처리를 한다."""
    try:
        btn = page.get_by_role("button", name=_L["audio_overview"][0], exact=False).first
        btn.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return
    elapsed = 0
    while elapsed < timeout_ms:
        cls = btn.get_attribute("class") or ""
        if "disabled-tile" not in cls:
            return
        page.wait_for_timeout(step_ms)
        elapsed += step_ms


def _fill_urls(page, urls: list[str]) -> bool:
    """URL 입력 상자를 찾아 줄바꿈으로 구분해 한 번에 넣는다.
    이 화면은 '여러 URL을 추가하려면 공백이나 줄 바꿈으로 구분하세요'라고 안내한다."""
    for ph in _L["url_box"]:
        try:
            box = page.get_by_placeholder(ph, exact=False).first
            box.wait_for(state="visible", timeout=10_000)
            box.fill("\n".join(urls))
            return True
        except Exception:
            continue
    # 배경의 웹 리서치 textarea에 URL을 넣으면 소스가 추가되지 않는다.
    return False


def _open_notebook(page, timeout_ms: int, notebook_url: str = "") -> str:
    """복구 주소가 있으면 재사용하고 없을 때만 새 노트북을 만든다."""
    if notebook_url:
        page.goto(notebook_url, wait_until="domcontentloaded", timeout=timeout_ms)
        return notebook_url
    return _create_notebook(page, timeout_ms)


def _capture_diagnostics(page, stage: str) -> None:
    """실패한 화면의 상태를 배치 로그 디렉터리에 보존한다."""
    LOGS_DIR.mkdir(exist_ok=True)
    try:
        state = page.evaluate("""() => ({url: location.href, text: document.body.innerText,
          buttons: [...document.querySelectorAll('button')].map(e => ({text:e.innerText, label:e.getAttribute('aria-label'),disabled:e.disabled})),
          inputs: [...document.querySelectorAll('textarea,input')].map(e => ({placeholder:e.getAttribute('placeholder'),value:e.value}))})""")
        (LOGS_DIR / f"notebook-{stage}.log").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        page.screenshot(path=str(LOGS_DIR / f"notebook-{stage}.png"), full_page=True)
    except Exception as e:
        print(f"[Notebook] 진단 기록 실패: {type(e).__name__}")


def _run(urls: list[str], prompt: str, notebook_title: str = "", notebook_url: str = "") -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(NOTEBOOKLM_PROFILE_DIR),
            headless=NOTEBOOKLM_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(_STEP_TIMEOUT)
            ms = NOTEBOOKLM_TIMEOUT * 1000

            page.goto("https://notebook.google.com/", wait_until="domcontentloaded", timeout=ms)

            if "accounts.google.com" in page.url:
                print("[Notebook] 로그인이 필요하다. `python -m notebooklm login` 으로 먼저 로그인할 것")
                return ""

            # 날짜별 노트북을 만들고 복구할 때는 기존 주소에서 이어간다.
            notebook_url = _open_notebook(page, ms, notebook_url)
            if not notebook_url:
                return ""
            print(f"[Notebook] 노트북 준비: {notebook_url}", flush=True)

            page.wait_for_timeout(5_000)   # Angular 앱이 그려질 때까지 기다린다
            if not _open_source_dialog(page):
                print("[Notebook] 소스 추가 화면에 들어가지 못했다 (UI 변경 가능성)")
                return ""
            if not _fill_urls(page, urls):
                print("[Notebook] URL 입력란을 찾지 못했다")
                return ""
            _capture_diagnostics(page, "source-filled")
            if not _click_any(page, _L["insert"]):
                _capture_diagnostics(page, "insert-failed")
                print("[Notebook] '삽입' 버튼을 찾지 못했다")
                return ""

            # 소스 크롤링이 끝나야 스튜디오 버튼이 활성화된다
            page.wait_for_timeout(8_000)
            _wait_studio_ready(page)

            if not _click_any(page, _L["audio_overview"]):
                print("[Notebook] 'AI 오디오 오버뷰' 버튼을 찾지 못했다")
                return ""
            page.wait_for_timeout(2_000)

            fmt = _FORMATS.get(NOTEBOOKLM_FORMAT, _FORMATS["deep_dive"])
            _click_any(page, fmt, timeout=5_000)     # 기본값이 심층 분석이라 실패해도 진행

            if prompt:
                try:
                    box = page.get_by_role("textbox").last
                    box.click()
                    box.fill(prompt)
                except Exception:
                    pass

            if not _click_any(page, _L["generate"], exact=True):
                print("[Notebook] '생성' 버튼을 찾지 못했다")
                return ""

            # 소스를 넣으면 Gemini 가 제목을 자동 생성해 덮어쓰므로 맨 마지막에 설정한다
            page.wait_for_timeout(3_000)
            if notebook_title and _set_title(page, notebook_title):
                print(f"[Notebook] 제목: {notebook_title}")

            # 생성이 실제로 시작됐는지 확인한다 (완료까지 기다리지는 않는다)
            _capture_diagnostics(page, "audio-requested")
            body = page.inner_text("body")
            started = any(k in body for k in _L["generating"])
            print(f"[Notebook] 오디오 오버뷰 생성 {'시작됨' if started else '요청함'}: "
                  f"{notebook_url}")
            return notebook_url
        finally:
            ctx.close()


def generate_audio_review(urls: list[str], title: str = "", date_str: str = "",
                          notebook_url: str = "") -> str:
    """새 노트북을 만들어 링크를 올리고 오디오 오버뷰 생성을 시킨다.
    성공하면 노트북 주소, 실패하면 빈 문자열.
    제목은 "[Daily] YY.MM.DD 헤드라인" 으로 붙인다."""
    urls = [u for u in urls if u]
    if not urls:
        return ""
    prompt = (f"{title} 오늘의 주요 기술 소식이야. 각 글의 핵심이 무엇인지, "
              f"서로 어떤 흐름으로 이어지는지 짚어줘.") if title else ""
    notebook_title = _notebook_title(date_str, title) if date_str else ""
    try:
        if notebook_url:
            return _run(urls, prompt, notebook_title, notebook_url=notebook_url)
        return _run(urls, prompt, notebook_title)
    except Exception as e:
        print(f"[Notebook] 실패: {type(e).__name__}: {str(e)[:150]}")
        return ""


def _audio_status(page) -> str:
    """오디오 예약·생성 중·재생 가능 상태를 화면에서 구분한다."""
    text = page.inner_text("body")
    if "예약됨" in text or "Scheduled" in text:
        return "scheduled"
    if re.search(r"생성\s*중|Generating", text):
        return "generating"
    if page.locator("audio").count():
        return "ready"
    return "unknown"


def inspect_audio_review(notebook_url: str) -> str:
    """기존 노트북을 변경하지 않고 오디오 생성 상태만 확인한다."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(NOTEBOOKLM_PROFILE_DIR), headless=NOTEBOOKLM_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(notebook_url, wait_until="domcontentloaded", timeout=NOTEBOOKLM_TIMEOUT * 1000)
            page.wait_for_timeout(6_000)
            status = _audio_status(page)
            _capture_diagnostics(page, "audio-status")
            return status
        finally:
            ctx.close()


def login() -> None:
    """최초 1회 로그인용. 창을 띄워 사용자가 직접 로그인하면 프로필에 세션이 저장된다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(NOTEBOOKLM_PROFILE_DIR), headless=False,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://notebook.google.com/")
        print("열린 창에서 Google 로그인을 마친 뒤 이 터미널에서 Enter 를 누르세요.")
        input()
        ctx.close()
        print(f"세션 저장 완료: {NOTEBOOKLM_PROFILE_DIR}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    else:
        print("사용법: python -m notebooklm login")
