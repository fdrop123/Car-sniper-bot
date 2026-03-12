"""
AutoTrader scraper using Playwright with debug screenshot.
"""
import asyncio
import logging
import re
import os
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
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-GB")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # Save screenshot and HTML for debugging
            await page.screenshot(path="debug_autotrader.png", full_page=False)
            with open("debug_autotrader.html", "w") as f:
                f.write(await page.content())
            logger.info(f"AutoTrader: page title = {await page.title()}")
            logger.info(f"AutoTrader: URL after load = {page.url}")

            soup = BeautifulSoup(await page.content(), "lxml")

            # Log all unique tag+class combos to find correct selectors
            all_articles = soup.select("article")
            all_lis = soup.select("li[class]")
            logger.info(f"AutoTrader: found {len(all_articles)} <article> tags, {len(all_lis)} <li> tags")

            cards = (
                soup.select("li[data-testid='search-result-with-image']") or
                soup.select("li[data-testid='search-result']") or
                soup.select("article.search-result") or
                soup.select("li.search-result") or
                soup.select("[data-testid='search-result']") or
                soup.select("section[data-testid='search-results'] > ul > li")
            )

            logger.info(f"AutoTrader: matched {len(cards)} cards")

            for card in cards:
                try:
                    title_el = card.select_one("h3") or card.select_one("[data-testid='search-result-title']")
                    price_el = card.select_one("[data-testid='search-result-price']") or card.select_one(".price-section")
                    link_el = card.select_one("a[href*='/car-details/']") or card.select_one("a[href*='/cars/']")

                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title:
                        continue
                    price_raw = price_el.get_text(strip=True) if price_el else "0"
                    digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                    price = int(digits) if digits else 0
                    if not link_el:
                        continue
                    href = link_el.get("href", "")
                    link = "https://www.autotrader.co.uk" + href if href.startswith("/") else href
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
