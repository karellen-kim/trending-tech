import requests
from bs4 import BeautifulSoup
from config import MAX_GITHUB_ITEMS

TRENDING_URL = "https://github.com/trending"

def fetch_trending(since: str = "daily") -> list[dict]:
    resp = requests.get(TRENDING_URL, params={"since": since}, timeout=15,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for article in soup.select("article.Box-row")[:MAX_GITHUB_ITEMS]:
        a = article.select_one("h2 a")
        if not a:
            continue
        path = a["href"].strip("/")
        desc_el = article.select_one("p.col-9")
        stars_el = article.select_one("a[href$='/stargazers']")
        items.append({
            "name": path,
            "url": f"https://github.com/{path}",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "stars_today": stars_el.get_text(strip=True) if stars_el else "",
        })
    return items
