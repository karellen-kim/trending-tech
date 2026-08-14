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

from config import (NOTEBOOKLM_NOTEBOOK_URL, NOTEBOOKLM_PROFILE_DIR, NOTEBOOKLM_FORMAT,
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
}
_FORMATS = {
    "deep_dive": ["심층 분석", "Deep Dive"],
    "summary": ["요약", "Summary"],
    "criticism": ["비평", "Critique"],
    "debate": ["토론", "Debate"],
}
_STEP_TIMEOUT = 30_000   # 개별 UI 조작 대기(ms)


def _click_any(page, labels, timeout=_STEP_TIMEOUT) -> bool:
    """여러 후보 라벨 중 먼저 보이는 것을 클릭한다."""
    deadline = timeout
    for label in labels:
        for target in (page.get_by_role("button", name=label, exact=False),
                       page.get_by_text(label, exact=False)):
            try:
                el = target.first
                el.wait_for(state="visible", timeout=deadline // max(len(labels), 1))
                el.click()
                return True
            except Exception:
                continue
    return False


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
    try:
        box = page.locator("textarea").first
        box.wait_for(state="visible", timeout=5_000)
        box.fill("\n".join(urls))
        return True
    except Exception:
        return False


def _run(urls: list[str], prompt: str) -> bool:
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
            page.goto(NOTEBOOKLM_NOTEBOOK_URL, wait_until="domcontentloaded",
                      timeout=NOTEBOOKLM_TIMEOUT * 1000)

            if "accounts.google.com" in page.url:
                print("[Notebook] 로그인이 필요하다. `python -m notebooklm login` 으로 먼저 로그인할 것")
                return False

            if not _click_any(page, _L["add_source"]):
                print("[Notebook] '출처 추가' 버튼을 찾지 못했다 (UI 변경 가능성)")
                return False
            if not _click_any(page, _L["website"]):
                print("[Notebook] '웹사이트' 항목을 찾지 못했다")
                return False
            if not _fill_urls(page, urls):
                print("[Notebook] URL 입력란을 찾지 못했다")
                return False
            if not _click_any(page, _L["insert"]):
                print("[Notebook] '삽입' 버튼을 찾지 못했다")
                return False

            # 소스 크롤링이 끝나야 스튜디오 버튼이 활성화된다
            page.wait_for_timeout(8_000)

            if not _click_any(page, _L["audio_overview"]):
                print("[Notebook] 'AI 오디오 오버뷰' 버튼을 찾지 못했다")
                return False
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

            if not _click_any(page, _L["generate"]):
                print("[Notebook] '생성' 버튼을 찾지 못했다")
                return False

            # 생성이 실제로 시작됐는지 확인한다 (완료까지 기다리지는 않는다)
            page.wait_for_timeout(3_000)
            body = page.inner_text("body")
            started = any(k in body for k in _L["generating"])
            print(f"[Notebook] 오디오 오버뷰 생성 {'시작됨' if started else '요청함'}: "
                  f"{NOTEBOOKLM_NOTEBOOK_URL}")
            return True
        finally:
            ctx.close()


def generate_audio_review(urls: list[str], title: str = "") -> bool:
    """링크를 노트북에 올리고 오디오 오버뷰 생성을 시킨다. 성공하면 True."""
    urls = [u for u in urls if u]
    if not urls:
        return False
    if not NOTEBOOKLM_NOTEBOOK_URL:
        print("[Notebook] NOTEBOOKLM_NOTEBOOK_URL 이 없다 — 노트북 주소를 .env 에 넣을 것")
        return False
    prompt = (f"{title}의 주요 기술 소식이야. 각 글의 핵심이 무엇인지, "
              f"서로 어떤 흐름으로 이어지는지 짚어줘.") if title else ""
    try:
        return _run(urls, prompt)
    except Exception as e:
        print(f"[Notebook] 실패: {type(e).__name__}: {str(e)[:150]}")
        return False


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
