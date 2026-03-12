"""
eBay Motors scraper - searches for automatic cars near Luton
"""
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import logging

logger = logging.getLogger(__name__)

# Luton eBay distance search uses postcode LU1
EBAY_BASE = "https://www.ebay.co.uk"

def get_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
    }

def scrape_ebay(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    """Scrape eBay Motors for automatic cars near Luton"""
    listings = []
    page = 1

    while True:
        # eBay Motors category 9801 = Cars
        # Transmission: 10015 = Automatic
        url = (
            f"{EBAY_BASE}/sch/Cars/9801/i.html"
            f"?_sacat=9801"
            f"&_udlo={min_price}"
            f"&_udhi={max_price}"
            f"&_fpos={postcode.replace(' ', '+')}"
            f"&_fsradm={radius}"
            f"&LH_ItemCondition=3000"   # used
            f"&Cars_Transmission=Automatic"
            f"&_mPrRngCbx=1"
            f"&_pgn={page}"
            f"&_ipg=60"
        )

        try:
            resp = requests.get(url, headers=get_headers(), timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"eBay request failed (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("li.s-item")

        if not items:
            logger.info(f"eBay: no more results at page {page}")
            break

        for item in items:
            try:
                title_el = item.select_one(".s-item__title")
                price_el = item.select_one(".s-item__price")
                year_el = item.select_one(".s-item__subtitle") or item.select_one(".s-item__caption")
                link_el = item.select_one("a.s-item__link")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title or title == "Shop on eBay":
                    continue

                price_raw = price_el.get_text(strip=True) if price_el else "£0"
                # Handle price ranges like "£300.00 to £1,500.00"
                price_raw = price_raw.split(" to ")[0]
                price = int(''.join(filter(str.isdigit, price_raw.split(".")[0]))) if price_raw else 0

                specs = year_el.get_text(strip=True) if year_el else ""
                link = link_el["href"] if link_el else ""
                if not link:
                    continue

                # Extract year from title/specs
                year = extract_year(title + " " + specs)
                if year and year < min_year:
                    continue

                listing_id = link.split("/itm/")[-1].split("?")[0] if "/itm/" in link else link[-20:]

                listings.append({
                    "id": f"ebay_{listing_id}",
                    "source": "eBay",
                    "title": title,
                    "price": price,
                    "specs": specs,
                    "url": link,
                    "year": year,
                })

            except Exception as e:
                logger.warning(f"eBay: failed to parse item: {e}")

        # Check pagination
        next_btn = soup.select_one("a.pagination__next") or soup.select_one("[aria-label='Next page']")
        if not next_btn or page >= 5:  # cap at 5 pages
            break

        page += 1
        time.sleep(2)

    logger.info(f"eBay: found {len(listings)} listings")
    return listings


def extract_year(text):
    """Extract a 4-digit year between 2006 and current year from text"""
    import re
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    if matches:
        return int(matches[0])
    return None
