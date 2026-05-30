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
MAX_BLOG_ITEMS = 5

RSS_SOURCES = [
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Lilian Weng", "url": "https://lilianweng.github.io/index.xml"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed"},
    {"name": "Andrej Karpathy", "url": "https://karpathy.github.io/feed.xml"},
    {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/"},
]

ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",
    "https://rss.arxiv.org/rss/cs.LG",
    "https://rss.arxiv.org/rss/cs.CL",
]
