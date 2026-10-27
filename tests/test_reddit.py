from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sources import reddit


def _entry(title, post_id, html, published='2026-10-27T09:00:00Z', field='content'):
    return f'''<entry><id>t3_{post_id}</id><title>{title}</title>
      <link href="https://www.reddit.com/r/MachineLearning/comments/{post_id}/post/"/>
      <published>{published}</published><updated>{published}</updated>
      <{field} type="html"><![CDATA[{html}]]></{field}></entry>'''


def _fetch(entries, max_items=5):
    response = MagicMock()
    response.content = (f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>').encode()
    with patch('sources.reddit.requests.get', return_value=response), \
         patch('sources.reddit._today_cutoff', return_value=datetime(2026, 10, 27, tzinfo=timezone.utc)):
        return reddit.fetch_subreddit('MachineLearning', max_items=max_items)


def test_selfpost_preserves_only_actual_md_body():
    html = '''<!-- SC_OFF --><div class="md"><p>Training needs a held-out test set.</p>
      <p>Compare against <a href="https://example.com/baseline">a baseline</a>.</p>
      <script>tracking()</script><style>.hidden {display:none}</style></div><!-- SC_ON -->
      submitted by <a href="/user/author">author</a><br/>
      <a href="https://reddit.com/post">[link]</a><a href="https://reddit.com/comments">[comments]</a>'''
    item = _fetch(_entry('A research discussion', 'abc', html))[0]
    assert item['content'] == 'Training needs a held-out test set. Compare against a baseline .'
    assert item['summary'] == ''
    assert item['source'] == 'r/MachineLearning'
    assert item['url'] == 'https://www.reddit.com/r/MachineLearning/comments/abc/post/'


def test_linkpost_does_not_turn_metadata_into_body():
    html = '''<table><tr><td><a href="https://example.com/article"><img alt="Article title" src="thumb.jpg"/></a></td>
      <td>submitted by <a href="/user/author">author</a><br/>
      <a href="https://example.com/article">[link]</a> <a href="https://reddit.com/comments">[comments]</a></td></tr></table>'''
    assert _fetch(_entry('External article', 'def', html))[0]['content'] == ''


def test_summary_field_can_supply_actual_selfpost_body():
    item = _fetch(_entry('Summary fallback', 'ghi', '<div class="md"><p>Actual text.</p></div>', field='summary'))[0]
    assert item['content'] == 'Actual text.'


def test_content_extraction_preserves_date_filter_and_limit():
    entries = _entry('Old', 'old', '<div class="md">Old body</div>', published='2026-10-26T09:00:00Z')
    entries += _entry('First', 'first', '<div class="md">First body</div>')
    entries += _entry('Second', 'second', '<div class="md">Second body</div>')
    items = _fetch(entries, max_items=1)
    assert len(items) == 1
    assert items[0]['title'] == 'First'
    assert items[0]['content'] == 'First body'


def test_metadata_only_content_does_not_hide_summary_body():
    entry = _entry('Body in summary', 'jkl', '<a href="https://reddit.com/comments">[comments]</a>')
    entry = entry.replace('</entry>', '<summary type="html"><![CDATA[<div class="md">Actual summary body.</div>]]></summary></entry>')
    assert _fetch(entry)[0]['content'] == 'Actual summary body.'


def test_longest_actual_body_wins_over_short_content():
    entry = _entry('Body in summary', 'mno', '<div class="md">Short</div>')
    entry = entry.replace('</entry>', '<summary type="html"><![CDATA[<div class="md">The complete actual body.</div>]]></summary></entry>')
    assert _fetch(entry)[0]['content'] == 'The complete actual body.'
