"""
AutoTrader scraper using their internal search API endpoint.
"""
import time
import logging
import re
import requests

logger = logging.getLogger(__name__)

def scrape_autotrader(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    listings = []

    # AutoTrader's internal API used by their own frontend
    url = "https://www.autotrader.co.uk/at-gateway?query=SearchResultsPage"

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json",
        "Accept-Language": "en-GB,en;q=0.9",
        "Origin": "https://www.autotrader.co.uk",
        "Referer": "https://www.autotrader.co.uk/",
        "Content-Type": "application/json",
    }

    payload = {
        "operationName": "SearchResultsPage",
        "variables": {
            "filters": {
                "postcode": postcode,
                "radius": str(radius),
                "priceFrom": str(min_price),
                "priceTo": str(max_price),
                "yearFrom": str(min_year),
                "transmission": ["Automatic"],
                "condition": ["Used"],
            },
            "page": 1,
            "pageSize": 100,
            "sortOrder": "relevance",
        },
        "query": """
        query SearchResultsPage($filters: SearchFilters, $page: Int, $pageSize: Int, $sortOrder: String) {
          search(filters: $filters, page: $page, pageSize: $pageSize, sortOrder: $sortOrder) {
            results {
              id title price year mileage transmission url
            }
            totalResults
          }
        }
        """
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", {}).get("search", {}).get("results", [])
            for r in results:
                listings.append({
                    "id": f"autotrader_{r.get('id', '')}",
                    "source": "AutoTrader",
                    "title": r.get("title", "Unknown"),
                    "price": r.get("price", 0),
                    "specs": f"{r.get('year', '')} • {r.get('mileage', '')} miles • {r.get('transmission', '')}",
                    "url": f"https://www.autotrader.co.uk{r.get('url', '')}",
                })
    except Exception as e:
        logger.error(f"AutoTrader API failed: {e}")

    # Fallback: try mobile site
    if not listings:
        listings = _scrape_autotrader_mobile(min_price, max_price, min_year, radius, postcode)

    logger.info(f"AutoTrader: found {len(listings)} listings")
    return listings


def _scrape_autotrader_mobile(min_price, max_price, min_year, radius, postcode):
    """Fallback mobile scraper"""
    listings = []
    try:
        import cloudscraper
        from bs4 import BeautifulSoup
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        url = (
            "https://www.autotrader.co.uk/car-search"
            f"?sort=relevance&radius={radius}"
            f"&postcode={postcode.replace(' ', '%20')}"
            f"&price-from={min_price}&price-to={max_price}"
            f"&year-from={min_year}&transmission=Automatic"
        )
        resp = scraper.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "lxml")
        cards = (
            soup.select("li[data-testid='search-result-with-image']") or
            soup.select("article.search-result") or
            soup.select("li.search-result")
        )
        for card in cards:
            try:
                title_el = card.select_one("h3") or card.select_one("[data-testid='search-result-title']")
                price_el = card.select_one("[data-testid='search-result-price']") or card.select_one(".price-section")
                link_el = card.select_one("a[href*='/car-details/']")
                title = title_el.get_text(strip=True) if title_el else "Unknown"
                price_raw = price_el.get_text(strip=True) if price_el else "0"
                digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                price = int(digits) if digits else 0
                if not link_el:
                    continue
                link = "https://www.autotrader.co.uk" + link_el["href"]
                lid = re.sub(r'\?.*', '', link.split("/")[-1])
                listings.append({
                    "id": f"autotrader_{lid}",
                    "source": "AutoTrader",
                    "title": title,
                    "price": price,
                    "specs": "",
                    "url": link,
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"AutoTrader mobile fallback failed: {e}")
    return listings
