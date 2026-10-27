import json

import pytest

import main


@pytest.mark.parametrize('audio_url', [None, 'https://notebooklm.google.com/notebook/restored'])
def test_save_html_persists_optional_audio_url(tmp_path, monkeypatch, audio_url):
    monkeypatch.setattr(main, 'DOCS_DIR', tmp_path)
    data = {
        'date': '2026-10-24',
        'highlights': ['요약'],
        'github': [],
        'company_blogs': [],
    }
    if audio_url is not None:
        data['audio_url'] = audio_url

    assert main.save_html(data) == ['요약']
    saved = json.loads((tmp_path / '2026-10-24.json').read_text(encoding='utf-8'))
    expected = {
        'date': '2026-10-24',
        'highlights': ['요약'],
        'github_names': [],
        'seen_urls': [],
        'today_take': {},
        'important_links': [],
    }
    if audio_url is not None:
        expected['audio_url'] = audio_url
    assert saved == expected
    assert (tmp_path / '2026-10-24.html').exists()
    assert (tmp_path / 'index.html').exists()


def test_save_html_persists_separate_community_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DOCS_DIR', tmp_path)
    hn = [{'title': 'HN', 'title_ko': 'HN 번역', 'url': 'https://hn', 'summary': 'HN 요약', 'rank': 1}]
    reddit = [{'title': 'Reddit', 'title_ko': '번역', 'url': 'https://reddit', 'summary': '요약'}]
    data = {'date': '2026-10-26', 'github': [], 'company_blogs': [],
            'hn': hn, 'reddit': reddit, 'hn_date': '2026-10-26'}
    main.save_html(data)
    saved = json.loads((tmp_path / '2026-10-26.json').read_text())
    assert saved['hn'] == hn
    assert saved['reddit'] == reddit
    assert saved['hn_date'] == '2026-10-26'
    assert saved['seen_urls'] == ['https://hn', 'https://reddit']
