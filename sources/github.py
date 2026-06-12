import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MAX_GITHUB_ITEMS

TRENDING_URL = "https://github.com/trending"
README_MAX_CHARS = 3000

def _fetch_readme(path: str) -> str:
    url = f"https://raw.githubusercontent.com/{path}/HEAD/README.md"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return resp.text[:README_MAX_CHARS]
    except Exception:
        pass
    return ""

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

    with ThreadPoolExecutor(max_workers=len(items)) as ex:
        futures = {ex.submit(_fetch_readme, item["name"]): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            items[futures[future]]["readme"] = future.result()

    return items
