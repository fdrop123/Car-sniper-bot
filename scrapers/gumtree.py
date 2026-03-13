"""
Gumtree scraper - cars only, no vans.
"""
import asyncio
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage", "--disable-gpu",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

VAN_KEYWORDS = ["van", "transit", "sprinter", "vivaro", "ducato", "trafic",
                "pickup", "truck", "tipper", "panel van", "minibus"]

async def _scrape_async(min_price, max_price, min_year, radius_km, location):
    from playwright.async_api import async_playwright
    listings = []

    url = (
        "https://www.gumtree.com/search"
        f"?search_category=cars&search_location={location}"
        f"&distance={radius_km}&min_price={min_price}&max_price={max_price}"
        f"&vehicle_transmission=automatic"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-GB")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            soup = BeautifulSoup(await page.content(), "lxml")
            items = (
                soup.select("article.listing-maxi") or
                soup.select("article[class*='listing']") or
                soup.select("[data-q='search-result']") or
                soup.select("article")
            )
            logger.info(f"Gumtree: matched {len(items)} items")

            for item in items:
                try:
                    title_el = (
                        item.select_one("h2") or
                        item.select_one(".listing-title") or
                        item.select_one("[class*='title']")
                    )
                    price_el = (
                        item.select_one(".listing-price strong") or
                        item.select_one("[data-q='price']") or
                        item.select_one("[class*='price']")
                    )
                    link_el = item.select_one("a[href]")

                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title:
                        continue
                    if any(w in title.lower() for w in VAN_KEYWORDS):
                        continue

                    price_raw = price_el.get_text(strip=True) if price_el else "0"
                    digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                    price = int(digits) if digits else 0
                    if price and (price < min_price or price > max_price):
                        continue

                    href = link_el.get("href", "") if link_el else ""
                    if not href:
                        continue
                    link = href if href.startswith("http") else "https://www.gumtree.com" + href

                    if any(x in link for x in ["gumtree.com/p/", "gumtree.com/cars"]) is False:
                        if "gumtree.com" not in link:
                            continue

                    year = _extract_year(title)
                    if year and year < min_year:
                        continue

                    id_match = re.search(r'/(\d+)$', link)
                    lid = id_match.group(1) if id_match else link[-15:]
                    listings.append({
                        "id": f"gumtree_{lid}",
                        "source": "Gumtree",
                        "title": title,
                        "price": price,
                        "specs": "",
                        "url": link,
                        "year": year,
                    })
                except Exception as e:
                    logger.warning(f"Gumtree parse error: {e}")

        except Exception as e:
            logger.error(f"Gumtree scrape error: {e}")
        finally:
            await browser.close()

    return listings

def scrape_gumtree(min_price=300, max_price=1500, min_year=2006, radius=60, location="luton"):
    radius_km = int(radius * 1.60934)
    try:
        listings = asyncio.run(_scrape_async(min_price, max_price, min_year, radius_km, location))
    except Exception as e:
        logger.error(f"Gumtree scraper failed: {e}")
        listings = []
    logger.info(f"Gumtree: found {len(listings)} listings")
    return listings

def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
