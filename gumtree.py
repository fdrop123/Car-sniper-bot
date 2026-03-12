"""
Gumtree scraper - searches for automatic cars near Luton
"""
import requests
import time
import logging
import re
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

def get_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://www.gumtree.com/",
    }

def scrape_gumtree(min_price=300, max_price=1500, min_year=2006, radius=60, location="luton"):
    """Scrape Gumtree for automatic cars near Luton"""
    listings = []
    page = 1
    radius_km = int(radius * 1.60934)

    while True:
        url = (
            f"https://www.gumtree.com/search"
            f"?search_category=cars-vans-motorbikes"
            f"&search_location={location}"
            f"&distance={radius_km}"
            f"&min_price={min_price}"
            f"&max_price={max_price}"
            f"&vehicle_transmission=automatic"
            f"&page={page}"
        )

        try:
            resp = requests.get(url, headers=get_headers(), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Gumtree request failed (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Try multiple selectors for Gumtree's changing layout
        items = (
            soup.select("article.listing-maxi") or
            soup.select("li.result-row") or
            soup.select("[data-q='search-result']") or
            soup.select(".listing-results-row") or
            soup.select("a[href*='/cars/'][class*='listing']")
        )

        if not items:
            logger.info(f"Gumtree: no more results at page {page}")
            break

        found_any = False
        for item in items:
            try:
                title_el = item.select_one("h2") or item.select_one(".listing-title") or item.select_one("[class*='title']")
                price_el = item.select_one(".listing-price strong") or item.select_one("[data-q='price']") or item.select_one("[class*='price']")
                link_el = item.select_one("a[href*='/cars/']") or item.select_one("a[href*='/vans/']") or (item if item.name == "a" else None)

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                price_raw = price_el.get_text(strip=True) if price_el else "0"
                digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                price = int(digits) if digits else 0

                href = link_el.get("href", "") if link_el else ""
                link = href if href.startswith("http") else "https://www.gumtree.com" + href
                if not href:
                    continue

                year = _extract_year(title)
                if year and year < min_year:
                    continue

                id_match = re.search(r'/(\d+)$', link)
                listing_id = id_match.group(1) if id_match else link[-15:]
                found_any = True

                listings.append({
                    "id": f"gumtree_{listing_id}",
                    "source": "Gumtree",
                    "title": title,
                    "price": price,
                    "specs": "",
                    "url": link,
                    "year": year,
                })
            except Exception as e:
                logger.warning(f"Gumtree: failed to parse item: {e}")

        if not found_any or page >= 5:
            break

        next_btn = soup.select_one("a[aria-label='Next']") or soup.select_one(".pagination-next")
        if not next_btn:
            break

        page += 1
        time.sleep(2)

    logger.info(f"Gumtree: found {len(listings)} listings")
    return listings

def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
