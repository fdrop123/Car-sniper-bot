"""
AutoTrader scraper - searches for automatic cars near Luton
"""
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import logging

logger = logging.getLogger(__name__)

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def get_headers():
    ua = UserAgent()
    return {**HEADERS_BASE, "User-Agent": ua.random}

def scrape_autotrader(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    """Scrape AutoTrader for automatic cars near Luton"""
    listings = []
    page = 1

    while True:
        url = (
            f"https://www.autotrader.co.uk/car-search"
            f"?sort=relevance"
            f"&radius={radius}"
            f"&postcode={postcode.replace(' ', '%20')}"
            f"&price-from={min_price}"
            f"&price-to={max_price}"
            f"&year-from={min_year}"
            f"&transmission=Automatic"
            f"&page={page}"
        )

        try:
            resp = requests.get(url, headers=get_headers(), timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"AutoTrader request failed (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Find listing cards
        cards = soup.select("li[data-testid='search-result-with-image']") or \
                soup.select("article.search-result")

        if not cards:
            logger.info(f"AutoTrader: no more results at page {page}")
            break

        for card in cards:
            try:
                title_el = card.select_one("h3") or card.select_one("[data-testid='search-result-title']")
                price_el = card.select_one("[data-testid='search-result-price']") or card.select_one(".price-section")
                year_mileage_el = card.select_one("[data-testid='search-result-specs']")
                link_el = card.select_one("a[href*='/car-details/']")

                title = title_el.get_text(strip=True) if title_el else "Unknown"
                price_raw = price_el.get_text(strip=True) if price_el else "£0"
                price = int(''.join(filter(str.isdigit, price_raw))) if price_raw else 0
                specs = year_mileage_el.get_text(strip=True) if year_mileage_el else ""
                link = "https://www.autotrader.co.uk" + link_el["href"] if link_el else ""

                if not link:
                    continue

                listing_id = link.split("/")[-1].split("?")[0]

                listings.append({
                    "id": f"autotrader_{listing_id}",
                    "source": "AutoTrader",
                    "title": title,
                    "price": price,
                    "specs": specs,
                    "url": link,
                    "transmission": "Automatic",
                })

            except Exception as e:
                logger.warning(f"AutoTrader: failed to parse card: {e}")

        # Check for next page
        next_btn = soup.select_one("a[data-testid='pagination-next']") or \
                   soup.select_one("a[rel='next']")
        if not next_btn:
            break

        page += 1
        time.sleep(2)

    logger.info(f"AutoTrader: found {len(listings)} listings")
    return listings
