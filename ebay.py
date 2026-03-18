"""
eBay UK Motors scraper.

- Buy It Now listings: included if price <= max_price
- Auction listings: only included if time remaining <= 20 minutes AND current bid <= max_price
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebay.co.uk"
_CARS_CATEGORY = "9801"
_AUCTION_SNIPE_MINUTES = 20  # Only alert on auctions ending within this many minutes

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.ebay.co.uk/",
}


def _get(session: requests.Session, url: str) -> requests.Response | None:
    for attempt in range(3):
        try:
            resp = session.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            wait = 3 * (attempt + 1)
            logger.warning(f"eBay GET attempt {attempt + 1} failed ({exc}); retrying in {wait}s...")
            if attempt < 2:
                time.sleep(wait)
    return None


def _parse_price(text: str) -> int | None:
    text = text.split(" to ")[0]
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_year(text: str) -> str | None:
    match = re.search(r"\b(200[0-9]|201[0-9]|202[0-9])\b", text)
    return match.group(1) if match else None


def _parse_mileage(text: str) -> str | None:
    match = re.search(r"([\d,]+)\s*(?:miles?|mi)\b", text, re.IGNORECASE)
    return f"{match.group(1)} mi" if match else None


def _parse_time_left_minutes(text: str) -> int | None:
    """
    Parse eBay's time-left strings into total minutes.
    Examples: '18m left', '1h 4m left', '2d 3h left', '45s left'
    Returns None if the format is unrecognised or time is too long to care about.
    """
    text = text.lower().replace("left", "").strip()
    days    = re.search(r"(\d+)\s*d", text)
    hours   = re.search(r"(\d+)\s*h", text)
    minutes = re.search(r"(\d+)\s*m", text)

    if days:
        return 99999  # Way too long — skip

    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if minutes:
        total += int(minutes.group(1))

    return total if (hours or minutes) else None


def _is_auction(item) -> bool:
    """Detect whether an eBay listing is an auction (not Buy It Now)."""
    # eBay marks BIN listings with a specific badge
    bin_badge = item.select_one(".s-item__purchase-options-with-icon, [class*='buy-it-now']")
    if bin_badge:
        return False
    # Look for bid count or "bid" text as auction indicator
    bid_el = item.select_one(".s-item__bids, [class*='bid']")
    if bid_el and "bid" in bid_el.get_text(strip=True).lower():
        return True
    # Check time-left element — auctions always show a countdown
    time_el = item.select_one(".s-item__time-left, [class*='time-left']")
    if time_el:
        return True
    return False


def _build_url(min_price: int, max_price: int, page: int) -> str:
    return (
        f"{_BASE_URL}/sch/i.html"
        f"?_sacat={_CARS_CATEGORY}"
        f"&_nkw=automatic+car"
        f"&_udlo={min_price}"
        f"&_udhi={max_price}"
        f"&LH_PrefLoc=1"    # UK only
        f"&_sop=10"         # Sort: newly listed first
        f"&_pgn={page}"
        f"&_ipg=60"
        f"&rt=nc"
    )


def scrape_ebay(
    min_price: int,
    max_price: int,
    min_year: int,
    radius: int,
    postcode: str,
    max_pages: int = 5,
) -> list[dict]:
    listings: list[dict] = []
    seen_ids: set[str] = set()
    session = requests.Session()

    for page in range(1, max_pages + 1):
        url = _build_url(min_price, max_price, page)
        logger.debug(f"  eBay page {page}: {url}")
        resp = _get(session, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("li.s-item:not(.s-item--placeholder)")
        if not items:
            break

        new_on_page = 0
        for item in items:
            try:
                link = item.select_one("a.s-item__link")
                if not link:
                    continue
                href = link["href"].split("?")[0]
                item_id_match = re.search(r"/itm/(\d+)", href)
                if not item_id_match:
                    continue
                item_id = item_id_match.group(1)

                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Title
                title_el = item.select_one(".s-item__title, [class*='item__title']")
                title = title_el.get_text(strip=True) if title_el else "Unknown"
                if not title or "Shop on eBay" in title:
                    continue

                # Price
                price_el = item.select_one(".s-item__price, [class*='item__price']")
                price = _parse_price(price_el.get_text()) if price_el else None
                if price and (price < min_price or price > max_price):
                    continue

                # Year
                year = _parse_year(title)
                if year and int(year) < min_year:
                    continue

                # Auction vs BIN logic
                auction = _is_auction(item)
                if auction:
                    time_el = item.select_one(".s-item__time-left, [class*='time-left']")
                    time_text = time_el.get_text(strip=True) if time_el else ""
                    minutes_left = _parse_time_left_minutes(time_text)

                    if minutes_left is None or minutes_left > _AUCTION_SNIPE_MINUTES:
                        continue  # Too much time left — skip for now

                    logger.info(f"  🔔 Auction snipe! '{title}' — {time_text} remaining")

                # Mileage / location
                sub_el = item.select_one(".s-item__subtitle, .s-item__condition, [class*='item__sub']")
                mileage = _parse_mileage(sub_el.get_text(" ", strip=True)) if sub_el else None

                location_el = item.select_one(".s-item__location, [class*='item__location']")
                location = location_el.get_text(strip=True).replace("From ", "") if location_el else None

                # Time left label for auction listings
                time_el = item.select_one(".s-item__time-left, [class*='time-left']")
                time_left = time_el.get_text(strip=True) if time_el else None

                listing = {
                    "source":   "ebay",
                    "id":       f"eb_{item_id}",
                    "title":    title,
                    "price":    price,
                    "year":     year,
                    "mileage":  mileage,
                    "location": location,
                    "url":      href,
                    "auction":  auction,
                }
                if auction and time_left:
                    listing["time_left"] = time_left

                listings.append(listing)
                new_on_page += 1

            except (KeyError, AttributeError, ValueError):
                continue

        logger.debug(f"  eBay page {page}: {new_on_page} new item(s)")
        if new_on_page == 0:
            break

        next_btn = soup.select_one("a.pagination__next, a[aria-label='Next page'], [class*='pagination'] a[rel='next']")
        if not next_btn:
            break

        time.sleep(2.5)

    return listings
