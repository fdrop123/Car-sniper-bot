"""
Gumtree scraper - searches for automatic cars near Luton
"""
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import logging
import re

logger = logging.getLogger(__name__)

GUMTREE_BASE = "https://www.gumtree.com"

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

    # Convert radius to km (Gumtree uses km)
    radius_km = int(radius * 1.60934)

    while True:
        url = (
            f"{GUMTREE_BASE}/search"
            f"?search_category=cars-vans-motorbikes"
            f"&search_location={location}"
            f"&distance={radius_km}"
            f"&min_price={min_price}"
            f"&max_price={max_price}"
            f"&min_year={min_year}"
            f"&vehicle_transmission=automatic"
            f"&page={page}"
        )

        try:
            resp = requests.get(url, headers=get_headers(), timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Gumtree request failed (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Find listing articles
        items = soup.select("article.listing-maxi") or \
                soup.select("li.result-row") or \
                soup.select("[data-q='search-result']")

        if not items:
            # Try alternate selectors
            items = soup.select(".listing-results-row")

        if not items:
            logger.info(f"Gumtree: no more results at page {page}")
            break

        for item in items:
            try:
                title_el = item.select_one("h2") or item.select_one(".listing-title")
                price_el = item.select_one(".listing-price strong") or item.select_one("[data-q='price']")
                desc_el = item.select_one(".listing-description") or item.select_one("p.description")
                link_el = item.select_one("a[href*='/cars/']") or item.select_one("a.listing-link")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                price_raw = price_el.get_text(strip=True) if price_el else "£0"
                price = int(''.join(filter(str.isdigit, price_raw.split(".")[0]))) if price_raw else 0

                desc = desc_el.get_text(strip=True) if desc_el else ""

                # Build URL
                if link_el:
                    href = link_el.get("href", "")
                    link = href if href.startswith("http") else GUMTREE_BASE + href
                else:
                    continue

                # Extract year
                year = extract_year(title + " " + desc)
                if year and year < min_year:
                    continue

                # Extract listing ID from URL
                listing_id = re.search(r'/(\d+)$', link)
                listing_id = listing_id.group(1) if listing_id else link[-15:]

                listings.append({
                    "id": f"gumtree_{listing_id}",
                    "source": "Gumtree",
                    "title": title,
                    "price": price,
                    "specs": desc[:120],
                    "url": link,
                    "year": year,
                })

            except Exception as e:
                logger.warning(f"Gumtree: failed to parse item: {e}")

        next_btn = soup.select_one("a[aria-label='Next']") or soup.select_one(".pagination-next")
        if not next_btn or page >= 5:
            break

        page += 1
        time.sleep(2)

    logger.info(f"Gumtree: found {len(listings)} listings")
    return listings


def extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    if matches:
        return int(matches[0])
    return None
