"""
eBay UK Motors scraper.

Searches eBay's Cars, Vans & Trucks category (9801) for automatic cars
within the specified price range and location.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebay.co.uk"
_CARS_CATEGORY = "9801"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_year(title: str) -> str | None:
    match = re.search(r"\b(200[0-9]|201[0-9]|202[0-9])\b", title)
    return match.group(1) if match else None


def _parse_mileage(text: str) -> str | None:
    match = re.search(r"([\d,]+)\s*(?:miles?|mi)\b", text, re.IGNORECASE)
    return f"{match.group(1)} mi" if match else None


def _build_search_url(postcode: str, radius: int, min_price: int, max_price: int, page: int) -> str:
    postcode_enc = postcode.replace(" ", "")
    return (
        f"{_BASE_URL}/sch/i.html"
        f"?_sacat={_CARS_CATEGORY}"
        f"&_nkw=automatic+car"
        f"&_udlo={min_price}"
        f"&_udhi={max_price}"
        f"&LH_BIN=1"
        f"&LH_PrefLoc=1"
        f"&_stpos={postcode_enc}"
        f"&_radius={radius}"
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
    """Scrape eBay UK for automatic cars matching the given criteria."""
    listings: list[dict] = []
    seen_ids: set[str] = set()
    session = requests.Session()

    for page in range(1, max_pages + 1):
        url = _build_search_url(postcode, radius, min_price, max_price, page)
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

                title_el = item.select_one(".s-item__title")
                title = title_el.get_text(strip=True) if title_el else "Unknown"
                if "Shop on eBay" in title:
                    continue

                price_el = item.select_one(".s-item__price")
                price = _parse_price(price_el.get_text()) if price_el else None

                sub_el = item.select_one(".s-item__subtitle, .s-item__condition")
                mileage = _parse_mileage(sub_el.get_text()) if sub_el else None

                location_el = item.select_one(".s-item__location")
                location = location_el.get_text(strip=True).replace("From ", "") if location_el else None

                year = _parse_year(title)
                if year and int(year) < min_year:
                    continue

                listings.append({
                    "source":   "ebay",
                    "id":       f"eb_{item_id}",
                    "title":    title,
                    "price":    price,
                    "year":     year,
                    "mileage":  mileage,
                    "location": location,
                    "url":      href,
                })
                new_on_page += 1

            except (KeyError, AttributeError, ValueError):
                continue

        if new_on_page == 0:
            break

        next_btn = soup.select_one("a.pagination__next, a[aria-label='Next page']")
        if not next_btn:
            break

        time.sleep(2.5)

    return listings
