import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

MAX_GITHUB_ITEMS = 5
MAX_HN_ITEMS = 10
MAX_PAPER_ITEMS = 5
MAX_BLOG_ITEMS = 10
MAX_REDDIT_ITEMS = 5
MAX_SCRAPER_ITEMS = 5

RSS_SOURCES = [
    # 개인 개발자 블로그/SNS
    {"name": "Andrej Karpathy", "url": "https://karpathy.substack.com/feed", "category": "dev"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml", "category": "dev"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed", "category": "dev"},
    {"name": "François Chollet", "url": "https://fchollet.substack.com/feed", "category": "dev"},
    {"name": "Nathan Lambert", "url": "https://www.interconnects.ai/feed", "category": "dev"},
    {"name": "Nils Reimers", "url": "https://medium.com/feed/@nils_reimers", "category": "dev"},
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "category": "dev"},
    {"name": "Chip Huyen", "url": "https://huyenchip.com/feed.xml", "category": "dev"},
    {"name": "Eugene Yan", "url": "https://eugeneyan.com/rss/", "category": "dev"},
    {"name": "swyx", "url": "https://www.swyx.io/rss.xml", "category": "dev"},
    {"name": "Kent Beck", "url": "https://tidyfirst.substack.com/feed", "category": "dev"},
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom", "category": "dev"},
    {"name": "Julia Evans", "url": "https://jvns.ca/atom.xml", "category": "dev"},
    {"name": "Dan Luu", "url": "https://danluu.com/atom.xml", "category": "dev"},
    {"name": "fast.ai", "url": "https://www.fast.ai/index.xml", "category": "dev"},
    {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/", "category": "dev"},
    # 기업 기술 블로그 (RSS)
    {"name": "Netflix Tech Blog", "url": "https://medium.com/feed/netflix-techblog", "category": "company"},
    {"name": "Meta Engineering", "url": "https://engineering.fb.com/feed/", "category": "company"},
    {"name": "Cloudflare Blog", "url": "https://blog.cloudflare.com/rss/", "category": "company"},
]

REDDIT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "programming",
    "artificial",
    "webdev",
    "devops",
]

SCRAPER_SOURCES = [
    {"name": "Alibaba Cloud Blog", "url": "https://www.alibabacloud.com/blog"},
    {"name": "Spotify Engineering", "url": "https://engineering.atspotify.com/"},
]

ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",
    "https://rss.arxiv.org/rss/cs.LG",
    "https://rss.arxiv.org/rss/cs.CL",
]
