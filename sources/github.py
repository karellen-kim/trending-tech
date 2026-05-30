import requests
from bs4 import BeautifulSoup
from config import MAX_GITHUB_ITEMS

TRENDING_URL = "https://github.com/trending"

def fetch_trending(since: str = "daily", exclude: set[str] | None = None) -> list[dict]:
    resp = requests.get(TRENDING_URL, params={"since": since}, timeout=15,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    exclude = exclude or set()
    items = []
    for article in soup.select("article.Box-row"):
        if len(items) >= MAX_GITHUB_ITEMS:
            break
        a = article.select_one("h2 a")
        if not a:
            continue
        path = a["href"].strip("/")
        if path in exclude:
            continue
        desc_el = article.select_one("p.col-9")
        stars_el = article.select_one("a[href$='/stargazers']")
        items.append({
            "name": path,
            "url": f"https://github.com/{path}",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "stars_today": stars_el.get_text(strip=True) if stars_el else "",
        })
    return items
