import config


def test_rss_sources_have_required_keys():
    for s in config.RSS_SOURCES:
        assert set(s.keys()) == {"name", "url", "category"}, s
        assert s["category"] in ("company", "dev"), s
        assert s["url"].startswith("http"), s


def test_no_duplicate_names_or_urls():
    names = [s["name"] for s in config.RSS_SOURCES]
    urls = [s["url"] for s in config.RSS_SOURCES]
    assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
    assert len(urls) == len(set(urls)), [u for u in urls if urls.count(u) > 1]


def test_scraper_and_rss_do_not_overlap():
    """같은 소스가 양쪽에 있으면 main.py 에서 company_blogs 에 중복 수집된다"""
    rss_names = {s["name"] for s in config.RSS_SOURCES}
    scraper_names = {s["name"] for s in config.SCRAPER_SOURCES}
    assert not (rss_names & scraper_names), rss_names & scraper_names


def test_broken_feed_removed():
    urls = {s["url"] for s in config.RSS_SOURCES}
    assert "https://www.deeplearning.ai/the-batch/feed/" not in urls  # HTTP 404 실측


def test_top_n_limit_is_three():
    assert config.MAX_BLOG_ITEMS == 3
    assert config.MAX_SCRAPER_ITEMS == 3


def test_source_count_expanded():
    assert len(config.RSS_SOURCES) >= 55
