import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

MAX_GITHUB_ITEMS = 10
MAX_HN_ITEMS = 10
MAX_PAPER_ITEMS = 5
MAX_BLOG_ITEMS = 10

RSS_SOURCES = [
    # AI 연구자
    {"name": "Andrej Karpathy", "url": "https://karpathy.substack.com/feed"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed"},
    {"name": "François Chollet", "url": "https://fchollet.substack.com/feed"},
    {"name": "Nathan Lambert", "url": "https://www.interconnects.ai/feed"},
    # AI 엔지니어링
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Chip Huyen", "url": "https://huyenchip.com/feed.xml"},
    {"name": "Eugene Yan", "url": "https://eugeneyan.com/rss/"},
    {"name": "swyx", "url": "https://www.swyx.io/rss.xml"},
    # 소프트웨어 엔지니어링
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
    {"name": "Julia Evans", "url": "https://jvns.ca/atom.xml"},
    {"name": "Dan Luu", "url": "https://danluu.com/atom.xml"},
    {"name": "fast.ai", "url": "https://www.fast.ai/index.xml"},
    # 뉴스레터
    {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/"},
]

ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",
    "https://rss.arxiv.org/rss/cs.LG",
    "https://rss.arxiv.org/rss/cs.CL",
]
