from datetime import datetime
from unittest.mock import patch
from sources import scraper


def _today_label():
    """고정 날짜를 쓰면 _is_recent 범위 밖으로 밀려나 시간이 지나면 깨진다"""
    return datetime.now(scraper.KST).strftime('%B %d, %Y')


def test_alibaba_only_opens_top_n_articles():
    """목록 전체를 열면 요청이 34배가 된다(실측 34건) — 상위 max_items 건만 연다"""
    links = "".join(
        f'<a href="https://www.alibabacloud.com/blog/article-number-{i}-long-title_{i}">'
        f'Article Number {i} With A Long Title</a>' for i in range(10)
    )
    opened = []
    with patch("sources.scraper.requests.get") as g:
        g.return_value.text = f"<html><body>{links}</body></html>"
        g.return_value.status_code = 200
        g.return_value.raise_for_status = lambda: None
        with patch("sources.scraper._fetch_article_date",
                   side_effect=lambda u: opened.append(u) or _today_label()), \
             patch("sources.scraper._fetch_article_text", return_value="본문" * 200):
            items = scraper.fetch_alibaba(max_items=3)
    assert len(opened) == 3
    assert len(items) == 3


def test_alibaba_sets_pub_hint_unknown_when_no_date():
    html = ('<html><body>'
            '<a href="https://www.alibabacloud.com/blog/some-long-article-title_1">'
            'Some Long Article Title Here</a></body></html>')
    with patch("sources.scraper.requests.get") as g:
        g.return_value.text = html
        g.return_value.status_code = 200
        g.return_value.raise_for_status = lambda: None
        with patch("sources.scraper._fetch_article_date", return_value=""), \
             patch("sources.scraper._fetch_article_text", return_value="본문" * 200):
            items = scraper.fetch_alibaba()
    assert len(items) == 1
    assert items[0]["pub_hint"] == "unknown"


def test_alibaba_drops_old_article_in_code():
    """실측상 8/13 페이지의 Wan3.0 글은 May 21 발행이었다 — 코드에서 걸러야 한다"""
    html = ('<html><body>'
            '<a href="https://www.alibabacloud.com/blog/some-long-article-title_1">'
            'Some Long Article Title Here</a></body></html>')
    with patch("sources.scraper.requests.get") as g:
        g.return_value.text = html
        g.return_value.status_code = 200
        g.return_value.raise_for_status = lambda: None
        with patch("sources.scraper._fetch_article_date", return_value="May 21, 2026"), \
             patch("sources.scraper._fetch_article_text", return_value="본문" * 200):
            items = scraper.fetch_alibaba()
    assert items == []


def test_is_recent_covers_yesterday():
    from datetime import datetime, timedelta
    y = datetime.now(scraper.KST).date() - timedelta(days=1)
    assert scraper._is_recent(y.strftime("%B %d, %Y")) is True
    old = datetime.now(scraper.KST).date() - timedelta(days=30)
    assert scraper._is_recent(old.strftime("%B %d, %Y")) is False
    assert scraper._is_recent("") is False


def test_spotify_scraper_is_removed():
    assert not hasattr(scraper, "fetch_spotify")
    assert "Spotify Engineering" not in scraper._SCRAPERS


def test_every_scraper_source_has_an_implementation():
    import config
    for s in config.SCRAPER_SOURCES:
        assert s["name"] in scraper._SCRAPERS, f"{s['name']} 은 파서가 없어 조용히 스킵된다"


# ── 본문 인코딩 (LY Corp 실측: 한글이 mojibake 로 깨졌다) ──

class _FakeResp:
    """requests.Response 처럼 encoding 을 바꾸면 text 가 다시 디코딩되는 가짜 응답"""
    def __init__(self, raw: bytes, encoding: str, apparent: str):
        self.content = raw
        self.encoding = encoding
        self.apparent_encoding = apparent

    @property
    def text(self):
        return self.content.decode(self.encoding, errors="replace")

    def raise_for_status(self):
        pass


def test_fetch_article_text_fixes_broken_encoding():
    """서버가 charset 을 안 주면 requests 는 ISO-8859-1 로 가정해 한글이 깨진다 (LY Corp 실측)"""
    from unittest.mock import patch
    from sources import scraper
    raw = ("<html><body><article>" + "안녕하세요 사내 보안 업무에 AI를 접목합니다. " * 8 +
           "</article></body></html>").encode("utf-8")
    resp = _FakeResp(raw, "ISO-8859-1", "utf-8")
    with patch("sources.scraper.requests.get", return_value=resp):
        out = scraper._fetch_article_text("http://x")
    assert "안녕하세요" in out, out[:60]
    assert "ì" not in out, "mojibake 가 남아 있다"


def test_fetch_article_text_keeps_declared_encoding():
    """서버가 charset 을 제대로 주면 건드리지 않는다"""
    from unittest.mock import patch
    from sources import scraper
    raw = "<html><body><article>정상 문서 내용</article></body></html>".encode("utf-8")
    resp = _FakeResp(raw, "utf-8", "euc-kr")
    with patch("sources.scraper.requests.get", return_value=resp):
        out = scraper._fetch_article_text("http://x")
    assert resp.encoding == "utf-8"
    assert "정상 문서 내용" in out
