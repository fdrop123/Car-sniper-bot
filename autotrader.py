"""
AutoTrader scraper using cloudscraper to bypass Cloudflare protection.
"""
import time
import logging
import re

logger = logging.getLogger(__name__)

def scrape_autotrader(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    try:
        import cloudscraper
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("cloudscraper not installed - run: pip install cloudscraper")
        return []

    listings = []
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

    page = 1
    while True:
        url = (
            "https://www.autotrader.co.uk/car-search"
            f"?sort=relevance&radius={radius}"
            f"&postcode={postcode.replace(' ', '%20')}"
            f"&price-from={min_price}&price-to={max_price}"
            f"&year-from={min_year}&transmission=Automatic&page={page}"
        )

        try:
            resp = scraper.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"AutoTrader request failed (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = (
            soup.select("li[data-testid='search-result-with-image']") or
            soup.select("article.search-result") or
            soup.select("[data-testid='search-result']") or
            soup.select("li.search-result")
        )

        if not cards:
            logger.info(f"AutoTrader: no more results at page {page}")
            break

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
            except Exception as e:
                logger.warning(f"AutoTrader parse error: {e}")

        next_btn = soup.select_one("a[data-testid='pagination-next']") or soup.select_one("a[rel='next']")
        if not next_btn:
            break
        page += 1
        time.sleep(3)

    logger.info(f"AutoTrader: found {len(listings)} listings")
    return listings
