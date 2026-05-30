import requests
from config import MAX_HN_ITEMS

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

def fetch_top_stories() -> list[dict]:
    resp = requests.get(ALGOLIA_URL, params={"tags": "front_page", "hitsPerPage": MAX_HN_ITEMS}, timeout=15)
    resp.raise_for_status()
    items = []
    for hit in resp.json().get("hits", [])[:MAX_HN_ITEMS]:
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append({
            "title": hit.get("title", ""),
            "url": url,
            "points": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "hn_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
        })
    return items
