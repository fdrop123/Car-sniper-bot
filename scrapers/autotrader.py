"""
AutoTrader scraper using Playwright headless browser to bypass IP blocking.
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

async def _scrape_async(min_price, max_price, min_year, radius, postcode):
    from playwright.async_api import async_playwright
    listings = []

    url = (
        "https://www.autotrader.co.uk/car-search"
        f"?sort=relevance&radius={radius}"
        f"&postcode={postcode.replace(' ', '%20')}"
        f"&price-from={min_price}&price-to={max_price}"
        f"&year-from={min_year}&transmission=Automatic"
        f"&body-type=Hatchback,Saloon,Estate,Coupe,Convertible,MPV,SUV"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-GB")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            page_num = 1
            while True:
                await page.goto(url + f"&page={page_num}", timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                soup = BeautifulSoup(await page.content(), "lxml")
                cards = (
                    soup.select("li[data-testid='search-result-with-image']") or
                    soup.select("article.search-result") or
                    soup.select("li.search-result")
                )

                if not cards:
                    logger.info(f"AutoTrader: no results at page {page_num}")
                    break

                for card in cards:
                    try:
                        title_el = card.select_one("h3") or card.select_one("[data-testid='search-result-title']")
                        price_el = card.select_one("[data-testid='search-result-price']") or card.select_one(".price-section")
                        specs_el = card.select_one("[data-testid='search-result-specs']")
                        link_el = card.select_one("a[href*='/car-details/']")

                        title = title_el.get_text(strip=True) if title_el else ""
                        if not title:
                            continue

                        price_raw = price_el.get_text(strip=True) if price_el else "0"
                        digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                        price = int(digits) if digits else 0

                        specs = specs_el.get_text(strip=True) if specs_el else ""
                        if not link_el:
                            continue
                        link = "https://www.autotrader.co.uk" + link_el["href"]
                        lid = re.sub(r'\?.*', '', link.split("/")[-1])

                        listings.append({
                            "id": f"autotrader_{lid}",
                            "source": "AutoTrader",
                            "title": title,
                            "price": price,
                            "specs": specs,
                            "url": link,
                        })
                    except Exception as e:
                        logger.warning(f"AutoTrader parse error: {e}")

                next_btn = soup.select_one("a[data-testid='pagination-next']") or soup.select_one("a[rel='next']")
                if not next_btn or page_num >= 3:
                    break
                page_num += 1
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"AutoTrader scrape error: {e}")
        finally:
            await browser.close()

    return listings

def scrape_autotrader(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    try:
        listings = asyncio.run(_scrape_async(min_price, max_price, min_year, radius, postcode))
    except Exception as e:
        logger.error(f"AutoTrader scraper failed: {e}")
        listings = []
    logger.info(f"AutoTrader: found {len(listings)} listings")
    return listings
