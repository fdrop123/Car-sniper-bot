"""
AutoTrader UK scraper.

Extracts listings from AutoTrader's embedded __NEXT_DATA__ JSON where possible,
falling back to HTML parsing if the JSON structure changes.
"""

import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.autotrader.co.uk"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.autotrader.co.uk/",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


def _get(session: requests.Session, url: str) -> requests.Response | None:
    for attempt in range(3):
        try:
            resp = session.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            wait = 3 * (attempt + 1)
            logger.warning(f"AutoTrader GET attempt {attempt + 1} failed ({exc}); retrying in {wait}s...")
            if attempt < 2:
                time.sleep(wait)
    return None


def _parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _extract_from_next_data(data: dict) -> list[dict]:
    """Pull advert list out of Next.js __NEXT_DATA__ blob."""
    listings: list[dict] = []
    try:
        adverts = (
            data["props"]["pageProps"]
            .get("advertList", data["props"]["pageProps"].get("initialState", {}))
            .get("adverts", [])
        )
    except (KeyError, AttributeError):
        return listings

    for ad in adverts:
        try:
            advert_id = str(ad.get("id", ""))
            make  = ad.get("make", "")
            model = ad.get("model", "")
            deriv = ad.get("derivative", "")
            year  = ad.get("year", "")
            title = " ".join(filter(None, [str(year), make, model, deriv])).strip()
            price = ad.get("price") or ad.get("advertisedPrice") or 0
            if isinstance(price, dict):
                price = price.get("amount", 0)

            mileage  = ad.get("mileage")
            location = ad.get("location", {})
            town     = location.get("town", "") if isinstance(location, dict) else ""

            listings.append({
                "source":   "autotrader",
                "id":       f"at_{advert_id}",
                "title":    title,
                "price":    int(price),
                "year":     str(year) if year else None,
                "mileage":  f"{mileage:,} mi" if mileage else None,
                "location": town,
                "url":      f"{_BASE_URL}/car-details/{advert_id}",
            })
        except (KeyError, ValueError, TypeError):
            continue
    return listings


def _extract_from_html(soup: BeautifulSoup) -> list[dict]:
    """Fallback HTML parsing when __NEXT_DATA__ doesn't have adverts."""
    listings: list[dict] = []
    cards = (
        soup.select("li[data-standout-type]")
        or soup.select("article[data-advert-card]")
        or soup.select("[class*='search-page__result']")
        or soup.select("[data-testid='advertTile']")
    )

    for card in cards:
        try:
            link = card.select_one("a[href*='/car-details/']")
            if not link:
                continue
            href = link["href"]
            advert_id = re.search(r"/car-details/([^/?#]+)", href)
            advert_id = advert_id.group(1) if advert_id else href

            title_el  = card.select_one("h3") or card.select_one("[class*='title']")
            price_el  = card.select_one("[data-testid='search-listing-price']") or card.select_one("[class*='price']")
            year_el   = card.select_one("[class*='year'], [data-testid*='year']")
            mileage_el = card.select_one("[class*='mileage'], [data-testid*='mileage']")

            title   = title_el.get_text(strip=True) if title_el else "Unknown"
            price   = _parse_price(price_el.get_text()) if price_el else None
            year    = year_el.get_text(strip=True) if year_el else None
            mileage = mileage_el.get_text(strip=True) if mileage_el else None
            full_url = f"{_BASE_URL}{href}" if href.startswith("/") else href

            listings.append({
                "source":   "autotrader",
                "id":       f"at_{advert_id}",
                "title":    title,
                "price":    price,
                "year":     year,
                "mileage":  mileage,
                "url":      full_url,
            })
        except (KeyError, AttributeError, ValueError):
            continue
    return listings


def scrape_autotrader(
    min_price: int,
    max_price: int,
    min_year: int,
    radius: int,
    postcode: str,
    max_pages: int = 5,
) -> list[dict]:
    """Scrape AutoTrader for automatic cars matching the given criteria."""
    postcode_clean = postcode.replace(" ", "")
    base_url = (
        f"{_BASE_URL}/car-search"
        f"?postcode={postcode_clean}"
        f"&radius={radius}"
        f"&year-from={min_year}"
        f"&price-from={min_price}"
        f"&price-to={max_price}"
        "&transmission=Automatic"
        "&sort=price-asc"
    )

    listings: list[dict] = []
    seen_ids: set[str] = set()
    session = requests.Session()

    # Visit homepage first to pick up cookies — helps avoid 403s
    try:
        session.get(_BASE_URL, headers=_HEADERS, timeout=10)
        time.sleep(1)
    except Exception:
        pass

    for page in range(1, max_pages + 1):
        url = f"{base_url}&page={page}"
        logger.debug(f"  AutoTrader page {page}: {url}")
        resp = _get(session, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")

        page_listings: list[dict] = []
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag and next_data_tag.string:
            try:
                page_listings = _extract_from_next_data(json.loads(next_data_tag.string))
            except json.JSONDecodeError:
                pass

        if not page_listings:
            page_listings = _extract_from_html(soup)

        if not page_listings:
            logger.debug("  No listings found — stopping pagination.")
            break

        for l in page_listings:
            if l["id"] not in seen_ids:
                seen_ids.add(l["id"])
                listings.append(l)

        has_next = bool(
            soup.select_one("a[aria-label='Next']")
            or soup.select_one("[data-testid='pagination-next']")
            or soup.select_one(".pagination__next:not([disabled])")
        )
        if not has_next:
            break

        time.sleep(2.5)

    return listings
