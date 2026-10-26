from concurrent.futures import Future
from unittest.mock import Mock

import pytest

import main
from summarizer import LlmCallError


def test_analysis_timeout_has_item_context(monkeypatch):
    monkeypatch.setattr(main, 'analyze_item', Mock(side_effect=LlmCallError('timeout', '600s')))
    with pytest.raises(LlmCallError, match='https://example.com/item'):
        main._analyze_items([{'title': 'Item', 'url': 'https://example.com/item', 'content': 'x' * 200}], 'summary')


@pytest.mark.parametrize('result, key, content', [
    ({'is_today': True, 'title_ko': '제목', 'summary': ''}, 'summary', 'x' * 200),
    ({'is_today': True, 'title_ko': ' ', 'summary': '요약'}, 'title', 'short'),
    ({'is_today': 'false', 'title_ko': '제목', 'summary': '요약'}, 'summary', 'x' * 200),
])
def test_analysis_rejects_missing_required_output(monkeypatch, result, key, content):
    monkeypatch.setattr(main, 'analyze_item', Mock(return_value=result))
    with pytest.raises(LlmCallError):
        main._analyze_items([{'title': 'Item', 'content': content}], key)


def test_analysis_outside_date_is_normal_filter(monkeypatch):
    monkeypatch.setattr(main, 'analyze_item', Mock(return_value={
        'is_today': False, 'pub_date': '2020-01-01', 'title_ko': '', 'summary': ''}))
    assert main._analyze_items([{'title': 'Old', 'content': 'x' * 200}], 'summary') == []


def test_analysis_title_only_and_short_content_allow_empty_summary(monkeypatch):
    monkeypatch.setattr(main, 'analyze_item', Mock(return_value={
        'is_today': True, 'pub_date': '', 'title_ko': '제목', 'summary': ''}))
    assert len(main._analyze_items([{'title': 'Community', 'content': 'x' * 200}], 'title', False)) == 1
    assert len(main._analyze_items([{'title': 'Short', 'content': 'short'}], 'summary', False)) == 1


def test_analysis_failure_cancels_queued_futures(monkeypatch):
    failed, queued = Future(), Future()
    failed.set_exception(LlmCallError('timeout', '600s'))
    executor = Mock()
    executor.submit.side_effect = [failed, queued]
    monkeypatch.setattr(main, 'ThreadPoolExecutor', Mock(return_value=executor))
    with pytest.raises(LlmCallError):
        main._analyze_items([{'title': 'Failed'}, {'title': 'Queued'}], 'title')
    assert queued.cancelled()
    executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_analysis_retains_input_order_when_completed_in_reverse(monkeypatch):
    monkeypatch.setattr(main, 'analyze_item', lambda title, *args, **kwargs: {
        'is_today': True, 'pub_date': '', 'title_ko': title, 'summary': ''})
    monkeypatch.setattr(main, 'as_completed', lambda futures: reversed(list(futures)))
    items = [{'title': 'First'}, {'title': 'Second'}]
    assert [item['title_ko'] for item in main._analyze_items(items, 'title', False)] == ['First', 'Second']


@pytest.mark.parametrize('failure', ['timeout', 'missing_take', 'blank_take'])
def test_main_blocks_publication_on_required_failure(monkeypatch, failure):
    data = {'date': '2026-10-27', 'github': [{'name': 'repo'}]}
    monkeypatch.setattr(main.signal, 'signal', Mock())
    monkeypatch.setattr(main.signal, 'alarm', Mock())
    monkeypatch.setattr(main, 'collect', Mock(return_value=data))
    summarize = Mock(return_value=data)
    if failure == 'timeout':
        summarize.side_effect = LlmCallError('timeout', '600s')
    elif failure == 'blank_take':
        data['today_take'] = {'headline': ' '}
    monkeypatch.setattr(main, 'summarize', summarize)
    publications = []
    for name in ['make_audio', 'save_html', 'save_weekly_page', 'save_monthly_page', 'git_commit_push', 'send_slack']:
        publication = Mock()
        monkeypatch.setattr(main, name, publication)
        publications.append(publication)
    with pytest.raises(LlmCallError):
        main.main()
    for publication in publications:
        publication.assert_not_called()
