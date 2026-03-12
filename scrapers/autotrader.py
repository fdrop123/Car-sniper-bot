"""
AutoTrader scraper - waits for JS-rendered results to load.
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
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            await page.goto(url, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5)

            # Wait for listing items to appear in the DOM
            try:
                await page.wait_for_selector("li.sc-1bwnykn-1", timeout=15000)
            except Exception:
                logger.info("AutoTrader: waiting for any li to load...")
                await asyncio.sleep(5)

            soup = BeautifulSoup(await page.content(), "lxml")

            # Use the confirmed class from debug logs
            cards = soup.select("li.sc-1bwnykn-1")

            # Fallback: any li containing a car-details link
            if not cards:
                cards = [li for li in soup.select("li") if li.select_one("a[href*='/car-details/']")]

            logger.info(f"AutoTrader: matched {len(cards)} cards")

            for card in cards:
                try:
                    link_el = card.select_one("a[href*='/car-details/']")
                    if not link_el:
                        continue

                    all_text = [el.get_text(strip=True) for el in card.select("h3, span, p, div") if el.get_text(strip=True)]

                    title_el = card.select_one("h3")
                    title = title_el.get_text(strip=True) if title_el else next((t for t in all_text if len(t) > 8 and "£" not in t), "")

                    price = 0
                    for t in all_text:
                        if "£" in t:
                            digits = ''.join(filter(str.isdigit, t.replace(",", "").split(".")[0]))
                            if digits and len(digits) <= 6:
                                price = int(digits)
                                break

                    href = link_el.get("href", "")
                    link = "https://www.autotrader.co.uk" + href if href.startswith("/") else href
                    lid = re.sub(r'\?.*', '', link.split("/")[-1])

                    if not title:
                        continue

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
