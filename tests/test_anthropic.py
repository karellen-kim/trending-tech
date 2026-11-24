from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest
import requests

from sources import anthropic


def response(html, url='https://www.anthropic.com/news'):
    value=requests.Response(); value.status_code=200; value.url=url
    value.encoding='utf-8'; value._content=html.encode()
    return value


def row(title, href, day, engineering=False):
    heading=f'<h3><a href="{href}">{title}</a></h3>' if engineering else f'<a href="{href}"><h3>{title}</h3></a>'
    return f'<li data-listing-row="{title}">{heading}<time>{day}</time></li>'


def article(day='2026-11-20'):
    return f'''<meta property="article:published_time" content="{day}T00:00:00Z">
    <main><article><header><h1>Title</h1><time datetime="{day}">{day}</time></header>
    <aside>RELATED OLD ARTICLE</aside><div class="hash_body"><h2>Actual heading</h2>
    <p class="post-text">Actual article body {'detail '*50}</p></div><footer>SUBSCRIBE</footer></article></main>'''


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(anthropic,'now_kst',lambda:datetime(2026,11,20,12,tzinfo=timezone(timedelta(hours=9))))


def test_news_filters_sorts_deduplicates_before_bounded_body_requests(clock,monkeypatch):
    listing='<nav>'+row('Nav','/news/nav','Nov 20, 2026')+'</nav><main>'
    listing+='<article><h3><a href="/news/featured">Featured</a></h3><time>Nov 20, 2026</time></article>'
    listing+=row('Old','/news/old','Nov 1, 2026')
    listing+=row('Yesterday','/news/yesterday','Nov 19, 2026')
    listing+=row('Newest','/news/newest','Nov 20, 2026')
    listing+=row('Repeated','https://anthropic.com/news/newest#details','Nov 20, 2026')
    listing+=row('Second','/claude-new','Nov 20, 2026')
    listing+=row('Fourth','/news/fourth','Nov 20, 2026')+'</main>'
    get=Mock(side_effect=[response(listing),response(article()),response(article()),response(article())])
    monkeypatch.setattr(anthropic.requests,'get',get)
    result=anthropic.fetch_anthropic_news(max_items=50)
    assert [x['title'] for x in result]==['Newest','Second','Fourth']
    assert get.call_count==4
    assert all(x['source']=='Anthropic News' and x['pub_date']=='2026-11-20' and x['date_verified'] for x in result)
    assert all('Actual heading' in x['content'] and 'RELATED' not in x['content'] and 'SUBSCRIBE' not in x['content'] for x in result)
    assert all(len(x['content'])<=2000 for x in result)


def test_engineering_research_links_and_empty_recent_window(clock,monkeypatch):
    listing='<main>'+row('Research','/research/evals','Nov 13, 2026',True)+'</main>'
    get=Mock(return_value=response(listing));monkeypatch.setattr(anthropic.requests,'get',get)
    assert anthropic.fetch_anthropic_engineering()==[]
    assert get.call_count==1
    monkeypatch.setattr(anthropic,'now_kst',lambda:datetime(2026,11,13,12,tzinfo=timezone(timedelta(hours=9))))
    get.side_effect=[response(listing),response(article('2026-11-13'))]
    result=anthropic.fetch_anthropic_engineering()
    assert result[0]['source']=='Anthropic Engineering'
    assert result[0]['url']=='https://www.anthropic.com/research/evals'


@pytest.mark.parametrize('href',['https://evil.test/news/x','javascript:alert(1)','//evil.test/x','https://www.anthropic.com.evil.test/x','http://anthropic.com/news/x','https://user@anthropic.com/news/x'])
def test_official_origin_only(clock,monkeypatch,href):
    get=Mock(return_value=response('<main>'+row('Unsafe',href,'Nov 20, 2026')+row('Old','/news/old','Nov 1, 2026')+'</main>'))
    monkeypatch.setattr(anthropic.requests,'get',get)
    assert anthropic.fetch_anthropic_news()==[]
    assert get.call_count==1


def test_undated_and_future_rows_excluded(clock,monkeypatch):
    listing='<main>'+row('No date','/news/no','unknown')+row('Future','/news/future','Nov 21, 2026')+'</main>'
    get=Mock(return_value=response(listing));monkeypatch.setattr(anthropic.requests,'get',get)
    assert anthropic.fetch_anthropic_news()==[]
    assert get.call_count==1


@pytest.mark.parametrize('html',['<main>No listing</main>','<main><div data-listing-row="empty"></div></main>'])
def test_malformed_listing_is_visible_failure(clock,monkeypatch,html):
    monkeypatch.setattr(anthropic.requests,'get',Mock(return_value=response(html)))
    with pytest.raises(ValueError):anthropic.fetch_anthropic_news()


@pytest.mark.parametrize('body',[article('2026-11-19'),'<article><p>Related card only</p></article>'])
def test_article_date_mismatch_or_missing_body_fails(clock,monkeypatch,body):
    monkeypatch.setattr(anthropic.requests,'get',Mock(side_effect=[response('<main>'+row('Article','/news/a','Nov 20, 2026')+'</main>'),response(body)]))
    with pytest.raises(ValueError):anthropic.fetch_anthropic_news()


def test_body_http_failure_propagates(clock,monkeypatch):
    get=Mock(side_effect=[response('<main>'+row('Article','/news/a','Nov 20, 2026')+'</main>'),requests.Timeout()])
    monkeypatch.setattr(anthropic.requests,'get',get)
    with pytest.raises(requests.Timeout):anthropic.fetch_anthropic_news()


def test_timestamp_dates_use_kst_and_date_only_stays_calendar(clock,monkeypatch):
    listing='<main>'+row('Article','/news/a','2026-11-19T16:00:00Z')+'</main>'
    monkeypatch.setattr(anthropic.requests,'get',Mock(side_effect=[response(listing),response(article())]))
    assert anthropic.fetch_anthropic_news()[0]['pub_date']=='2026-11-20'


def test_article_uses_own_header_date_when_metadata_absent(clock,monkeypatch):
    listing='<main>'+row('Article','/news/a','November 20, 2026')+'</main>'
    body=article().split('>',1)[1]
    monkeypatch.setattr(anthropic.requests,'get',Mock(side_effect=[response(listing),response(body)]))
    assert anthropic.fetch_anthropic_news()[0]['pub_hint']=='2026-11-20'


def test_redirect_outside_official_origin_is_rejected(clock,monkeypatch):
    monkeypatch.setattr(anthropic.requests,'get',Mock(return_value=response('<main>Content</main>','https://evil.test/article')))
    with pytest.raises(ValueError,match='origin'):anthropic.fetch_anthropic_news()


def test_conflicting_duplicate_dates_raise(clock,monkeypatch):
    listing='<main>'+row('A','/news/a','Nov 20, 2026')+row('A again','/news/a','Nov 19, 2026')+'</main>'
    monkeypatch.setattr(anthropic.requests,'get',Mock(return_value=response(listing)))
    with pytest.raises(ValueError,match='Conflicting'):anthropic.fetch_anthropic_news()


@pytest.mark.parametrize('report_day',['2026-11-20','2026-11-21'])
def test_listing_calendar_day_and_timestamp_rollover_use_canonical_kst(monkeypatch,report_day):
    monkeypatch.setattr(anthropic,'now_kst',lambda:datetime.fromisoformat(report_day+'T12:00:00+09:00'))
    listing='<main>'+row('Rollover','/news/a','Nov 19, 2026')+'</main>'
    body=article('2026-11-19').replace('2026-11-19T00:00:00Z','2026-11-19T16:00:00Z')
    get=Mock(side_effect=[response(listing),response(body)])
    monkeypatch.setattr(anthropic.requests,'get',get)
    result=anthropic.fetch_anthropic_news()
    assert len(result)==1
    assert result[0]['pub_date']==result[0]['pub_hint']=='2026-11-20'
    assert result[0]['date_verified']
    assert get.call_count==2


def test_future_canonical_article_date_is_filtered_after_detail(clock,monkeypatch):
    listing='<main>'+row('Future rollover','/news/a','Nov 20, 2026')+'</main>'
    body=article().replace('2026-11-20T00:00:00Z','2026-11-20T16:00:00Z')
    get=Mock(side_effect=[response(listing),response(body)])
    monkeypatch.setattr(anthropic.requests,'get',get)
    assert anthropic.fetch_anthropic_news()==[]
    assert get.call_count==2


def test_previous_coarse_day_outside_canonical_window_is_not_emitted(clock,monkeypatch):
    listing='<main>'+row('Old day','/news/a','Nov 18, 2026')+'</main>'
    get=Mock(side_effect=[response(listing),response(article('2026-11-18'))])
    monkeypatch.setattr(anthropic.requests,'get',get)
    assert anthropic.fetch_anthropic_news()==[]
    assert get.call_count==2


def test_launch_page_uses_hero_publication_time(clock, monkeypatch):
    listing='<main>'+row('Launch','/claude-new','Nov 20, 2026')+'</main>'
    body=article().replace('<meta property="article:published_time" content="2026-11-20T00:00:00Z">','')
    body=body.replace('<header><h1>Title</h1><time datetime="2026-11-20">2026-11-20</time></header>','')
    body=body.replace('<main>','<main><section aria-labelledby="launch-hero-title"><time datetime="2026-11-20">November 20, 2026</time><h1 id="launch-hero-title">Launch</h1></section>')
    monkeypatch.setattr(anthropic.requests,'get',Mock(side_effect=[response(listing),response(body)]))
    result=anthropic.fetch_anthropic_news()
    assert result[0]['pub_date']=='2026-11-20'
    assert 'Actual article body' in result[0]['content']
