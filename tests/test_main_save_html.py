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
