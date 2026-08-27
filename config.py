import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    """'지금'의 단일 출처. RUN_DATE(YYYY-MM-DD)가 있으면 그날 정오를 지금으로 본다.
    빠진 날짜를 소급해서 배치를 돌릴 때 수집 윈도우·날짜 판정·파일명이 함께 그날로 맞춰진다.
    정오를 쓰는 이유는 자정 경계에서 날짜가 흔들리지 않게 하기 위해서다."""
    s = os.getenv("RUN_DATE", "").strip()
    if not s:
        return datetime.now(KST)
    d = datetime.strptime(s, "%Y-%m-%d").date()
    return datetime(d.year, d.month, d.day, 12, tzinfo=KST)

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"
AUDIO_DIR = DOCS_DIR / "audio"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# Gemini Notebook(구 NotebookLM) 오디오 오버뷰. 준비 절차는 docs/notebooklm-setup.md 참고.
# 매일 새 노트북을 만들어 링크를 올리고 오디오를 생성시킨다.
# 기본은 꺼짐 — 로그인 세션이 준비돼야 동작한다.
ENABLE_NOTEBOOKLM = os.getenv("ENABLE_NOTEBOOKLM", "0") == "1"
NOTEBOOKLM_PROFILE_DIR = Path(os.getenv("NOTEBOOKLM_PROFILE_DIR",
                                        str(Path.home() / ".gemini-notebook-profile")))
NOTEBOOKLM_FORMAT = os.getenv("NOTEBOOKLM_FORMAT", "deep_dive")   # deep_dive|summary|criticism|debate
NOTEBOOKLM_LANGUAGE = os.getenv("NOTEBOOKLM_LANGUAGE", "ko")
NOTEBOOKLM_HEADLESS = os.getenv("NOTEBOOKLM_HEADLESS", "1") == "1"
NOTEBOOKLM_TIMEOUT = int(os.getenv("NOTEBOOKLM_TIMEOUT", "120"))

MAX_GITHUB_ITEMS = 5
MAX_HN_ITEMS = 10
MAX_PAPER_ITEMS = 5
MAX_BLOG_ITEMS = 3        # 소스당 검사할 최신 글 수
MAX_REDDIT_ITEMS = 5
MAX_SCRAPER_ITEMS = 3

COLLECT_DAYS = 2          # 오늘 포함 최근 N일 글을 수집 (하루치만 보면 5건 수준이라 2일)
MAX_COMPANY_TOTAL = 25    # 기술블로그 섹션 하루 전체 상한
MAX_DEV_TOTAL = 20        # 개발자블로그 섹션 하루 전체 상한
MAX_BODY_FETCH = 40       # 요약이 짧아 본문을 새로 받아올 최대 건수
ENABLE_SVG = True
MAX_SVG_ITEMS = 4         # 개념 SVG 생성 대상 상위 N건 (다이어그램 1건이 콘텐츠 2000자·180초 타임아웃으로 가장 무거운 호출)
SUMMARY_WORKERS = 4       # 분석(날짜판정+번역+요약) 병렬 실행 수
RSS_WORKERS = 8           # RSS 수집 병렬 실행 수

# 전부 실측 검증된 피드 (HTTP 200 + 엔트리 존재 + 날짜 파싱 가능)
RSS_SOURCES = [
    # AI·리서치
    {"name": "AWS ML Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "category": "company"},
    {"name": "Apple ML Research", "url": "https://machinelearning.apple.com/rss.xml", "category": "company"},
    {"name": "Google DeepMind", "url": "https://deepmind.google/discover/blog/feed", "category": "company"},
    {"name": "Google Research", "url": "https://research.google/blog/rss", "category": "company"},
    {"name": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/feed/", "category": "company"},
    # 빅테크 엔지니어링
    {"name": "AWS Architecture Blog", "url": "https://aws.amazon.com/blogs/architecture/feed/", "category": "company"},
    {"name": "Cloudflare Blog", "url": "https://blog.cloudflare.com/rss/", "category": "company"},
    {"name": "Confluent Blog", "url": "https://www.confluent.io/rss.xml", "category": "company"},
    {"name": "Databricks Blog", "url": "https://www.databricks.com/blog/feed.xml", "category": "company"},
    {"name": "Datadog Engineering", "url": "https://www.datadoghq.com/blog/engineering/index.xml", "category": "company"},
    {"name": "Discord Blog", "url": "https://discord.com/blog/rss.xml", "category": "company"},
    {"name": "Elastic Search Labs", "url": "https://www.elastic.co/search-labs/blog/feed", "category": "company"},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/", "category": "company"},
    {"name": "Meta Engineering", "url": "https://engineering.fb.com/feed/", "category": "company"},
    {"name": "Netflix Tech Blog", "url": "https://netflixtechblog.com/feed", "category": "company"},
    {"name": "Slack Engineering", "url": "https://slack.engineering/feed", "category": "company"},
    {"name": "Spotify Engineering", "url": "https://engineering.atspotify.com/feed", "category": "company"},
    {"name": "Vespa Blog", "url": "https://blog.vespa.ai/feed.xml", "category": "company"},
    # 국내
    {"name": "29CM 기술블로그", "url": "https://medium.com/feed/29cm", "category": "company"},
    {"name": "Hyperconnect Tech", "url": "https://hyperconnect.github.io/feed.xml", "category": "company"},
    {"name": "Kakao Tech", "url": "https://tech.kakao.com/blog/feed", "category": "company"},
    {"name": "LY Corp Tech", "url": "https://techblog.lycorp.co.jp/ko/feed/index.xml", "category": "company"},
    {"name": "NAVER D2", "url": "https://d2.naver.com/d2.atom", "category": "company"},
    {"name": "SK플래닛 기술블로그", "url": "https://techtopic.skplanet.com/rss.xml", "category": "company"},
    {"name": "Spoqa 기술블로그", "url": "https://spoqa.github.io/atom.xml", "category": "company"},
    {"name": "Toss Tech", "url": "https://toss.tech/rss.xml", "category": "company"},
    {"name": "무신사 기술블로그", "url": "https://medium.com/feed/musinsa-tech", "category": "company"},
    {"name": "뱅크샐러드 기술블로그", "url": "https://blog.banksalad.com/rss.xml", "category": "company"},
    {"name": "쏘카 기술블로그", "url": "https://tech.socarcorp.kr/rss.xml", "category": "company"},
    {"name": "왓챠 기술블로그", "url": "https://medium.com/feed/watcha", "category": "company"},
    {"name": "컬리 기술블로그", "url": "https://helloworld.kurly.com/rss.xml", "category": "company"},
    # 아키텍처·분산 시스템
    {"name": "Adrian Cockcroft", "url": "https://adrianco.medium.com/feed", "category": "dev"},
    {"name": "Aphyr (Kyle Kingsbury)", "url": "https://aphyr.com/posts.atom", "category": "dev"},
    {"name": "Brendan Gregg", "url": "https://www.brendangregg.com/blog/rss.xml", "category": "dev"},
    {"name": "Daniel Lemire", "url": "https://lemire.me/blog/feed/", "category": "dev"},
    {"name": "Dan Luu", "url": "https://danluu.com/atom.xml", "category": "dev"},
    {"name": "Gregor Hohpe", "url": "https://architectelevator.com/feed.xml", "category": "dev"},
    {"name": "Marc Brooker", "url": "https://brooker.co.za/blog/rss.xml", "category": "dev"},
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom", "category": "dev"},
    {"name": "Martin Kleppmann", "url": "https://feeds.feedburner.com/martinkl?format=xml", "category": "dev"},
    # AI·LLM
    {"name": "Andrej Karpathy", "url": "https://karpathy.bearblog.dev/feed/", "category": "dev"},
    {"name": "Chip Huyen", "url": "https://huyenchip.com/feed.xml", "category": "dev"},
    {"name": "Denny Britz", "url": "https://dennybritz.com/index.xml", "category": "dev"},
    {"name": "Hamel Husain", "url": "https://hamel.dev/index.xml", "category": "dev"},
    {"name": "Jay Alammar", "url": "https://jalammar.github.io/feed.xml", "category": "dev"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml", "category": "dev"},
    {"name": "Nathan Lambert", "url": "https://www.interconnects.ai/feed", "category": "dev"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed", "category": "dev"},
    {"name": "Yoshua Bengio", "url": "https://yoshuabengio.org/feed", "category": "dev"},
    {"name": "fast.ai", "url": "https://www.fast.ai/index.xml", "category": "dev"},
    {"name": "swyx", "url": "https://www.swyx.io/rss.xml", "category": "dev"},
    # 검색·추천·랭킹
    {"name": "Doug Turnbull", "url": "https://softwaredoug.com/feed.xml", "category": "dev"},
    {"name": "Eugene Yan", "url": "https://eugeneyan.com/rss", "category": "dev"},
    # ML 플랫폼·MLOps
    {"name": "Shreya Shankar", "url": "https://www.sh-reya.com/rss.xml", "category": "dev"},
    # 기타 개발자 블로그
    {"name": "Julia Evans", "url": "https://jvns.ca/atom.xml", "category": "dev"},
    {"name": "Kent Beck", "url": "https://tidyfirst.substack.com/feed", "category": "dev"},
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "category": "dev"},
]

REDDIT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "programming",
    "artificial",
    "webdev",
    "devops",
]

# RSS 를 제공하지 않아 스크래핑이 필요한 소스만 남긴다.
# Spotify·Discord 는 RSS 로 전환, Anthropic 은 RSS 도 파서도 없어 제거.
SCRAPER_SOURCES = [
    {"name": "Alibaba Cloud Blog", "url": "https://www.alibabacloud.com/blog"},
    {"name": "Uber Engineering", "url": "https://www.uber.com/en-US/blog/engineering/"},
]

ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",
    "https://rss.arxiv.org/rss/cs.LG",
    "https://rss.arxiv.org/rss/cs.CL",
]
