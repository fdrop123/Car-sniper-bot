"""
Gumtree UK scraper.

Searches Gumtree's Cars, Vans & Motorbikes category for automatic cars
in and around the specified location.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.gumtree.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.gumtree.com/",
}

# Gumtree distance values (closest match for given radius in miles)
_DISTANCE_MAP = {
    0: 0, 1: 1, 5: 5, 10: 10, 20: 20, 30: 30, 50: 50, 100: 100,
}


def _best_distance(radius: int) -> int:
    options = sorted(_DISTANCE_MAP.keys())
    return min(options, key=lambda x: abs(x - radius))


def _get(session: requests.Session, url: str) -> requests.Response | None:
    for attempt in range(3):
        try:
            resp = session.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            wait = 3 * (attempt + 1)
            logger.warning(f"Gumtree GET attempt {attempt + 1} failed ({exc}); retrying in {wait}s…")
            if attempt < 2:
                time.sleep(wait)
    return None


def _parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_year(text: str) -> str | None:
    match = re.search(r"\b(200[0-9]|201[0-9]|202[0-9])\b", text)
    return match.group(1) if match else None


def _parse_mileage(text: str) -> str | None:
    match = re.search(r"([\d,]+)\s*(?:miles?|mi)\b", text, re.IGNORECASE)
    return f"{match.group(1)} mi" if match else None


def _build_url(location: str, distance: int, min_price: int, max_price: int, min_year: int, page: int) -> str:
    slug = location.lower().replace(" ", "-")
    page_suffix = f"/page{page}" if page > 1 else ""
    return (
        f"{_BASE_URL}/search{page_suffix}"
        f"?search_category=cars-vans-motorbikes"
        f"&search_location={slug}"
        f"&distance={distance}"
        f"&min_price={min_price}"
        f"&max_price={max_price}"
        f"&vehicle_transmission=Automatic"
        f"&min_vehicle_year={min_year}"
        f"&sort=date"
    )


def scrape_gumtree(
    min_price: int,
    max_price: int,
    min_year: int,
    radius: int,
    postcode: str,
    location: str = "luton",
    max_pages: int = 5,
) -> list[dict]:
    """Scrape Gumtree for automatic cars matching the given criteria."""
    distance = _best_distance(radius)
    listings: list[dict] = []
    seen_ids: set[str] = set()
    session = requests.Session()

    for page in range(1, max_pages + 1):
        url = _build_url(location, distance, min_price, max_price, min_year, page)
        logger.debug(f"  Gumtree page {page}: {url}")
        resp = _get(session, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Gumtree listing cards
        articles = (
            soup.select("article.listing-maxi")
            or soup.select("li.listing-result")
            or soup.select("[data-q='search-result']")
            or soup.select(".natural-listing")
        )
        if not articles:
            break

        new_on_page = 0
        for article in articles:
            try:
                # Link & ID
                link = article.select_one("a[href*='/cars-vans-trucks/']") or article.select_one("a.listing-link")
                if not link:
                    # Try any internal href
                    link = article.select_one("a[href^='/']")
                if not link:
                    continue

                href = link["href"]
                item_id_match = re.search(r"/(\d+)(?:\?|$)", href)
                if not item_id_match:
                    continue
                item_id = item_id_match.group(1)

                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Title
                title_el = (
                    article.select_one("h2.listing-title")
                    or article.select_one("[class*='listing-title']")
                    or article.select_one("h2")
                )
                title = title_el.get_text(strip=True) if title_el else "Unknown"

                # Price
                price_el = (
                    article.select_one(".listing-price strong")
                    or article.select_one("[class*='listing-price']")
                    or article.select_one("[data-q='price']")
                )
                price = _parse_price(price_el.get_text()) if price_el else None

                # Description snippet — year / mileage often here
                desc_el = article.select_one(".listing-description, [class*='description']")
                desc_text = desc_el.get_text(" ", strip=True) if desc_el else ""

                year    = _parse_year(title) or _parse_year(desc_text)
                mileage = _parse_mileage(desc_text)

                if year and int(year) < min_year:
                    continue

                # Location
                location_el = article.select_one(".listing-location, [data-q='listing-location']")
                loc_text = location_el.get_text(strip=True) if location_el else None

                full_url = f"{_BASE_URL}{href}" if href.startswith("/") else href

                listings.append({
                    "source":   "gumtree",
                    "id":       f"gt_{item_id}",
                    "title":    title,
                    "price":    price,
                    "year":     year,
                    "mileage":  mileage,
                    "location": loc_text,
                    "url":      full_url,
                })
                new_on_page += 1

            except (KeyError, AttributeError, ValueError):
                continue

        if new_on_page == 0:
            break

        # Pagination
        next_btn = soup.select_one("a[rel='next'], a.pagination-next, [data-q='pagination-next']")
        if not next_btn:
            break

        time.sleep(2.5)

    return listings
