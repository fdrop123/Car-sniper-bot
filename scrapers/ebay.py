"""
eBay scraper - dismisses cookie banner before scraping.
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
        "https://www.ebay.co.uk/sch/i.html"
        f"?_sacat=9801&_udlo={min_price}&_udhi={max_price}"
        f"&_fpos={postcode.replace(' ', '+')}&_fsradm={radius}"
        f"&LH_ItemCondition=3000&Cars_Transmission=Automatic&_ipg=60"
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
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            for sel in [
                "button:has-text('Accept all')",
                "button:has-text('Accept All')",
                "#gdpr-banner-accept",
                "button[id*='accept']",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        logger.info(f"eBay: dismissed cookie banner")
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass

            await asyncio.sleep(3)
            await page.screenshot(path="debug_ebay.png", full_page=False)
            logger.info(f"eBay: title={await page.title()}, url={page.url}")

            soup = BeautifulSoup(await page.content(), "lxml")
            items = soup.select("li.s-item")
            logger.info(f"eBay: matched {len(items)} items")

            for item in items:
                try:
                    title_el = item.select_one(".s-item__title") or item.select_one("h3")
                    price_el = item.select_one(".s-item__price")
                    link_el = item.select_one("a.s-item__link") or item.select_one("a[href*='ebay.co.uk/itm']")

                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title or title.lower() == "shop on ebay":
                        continue
                    if any(w in title.lower() for w in ["van", "transit", "sprinter", "pickup"]):
                        continue

                    price_raw = (price_el.get_text(strip=True) if price_el else "0").split(" to ")[0]
                    digits = ''.join(filter(str.isdigit, price_raw.replace(",", "").split(".")[0]))
                    price = int(digits) if digits else 0

                    link = link_el["href"] if link_el else ""
                    if not link:
                        continue

                    year = _extract_year(title)
                    if year and year < min_year:
                        continue

                    lid = link.split("/itm/")[-1].split("?")[0] if "/itm/" in link else link[-20:]
                    listings.append({
                        "id": f"ebay_{lid}",
                        "source": "eBay",
                        "title": title,
                        "price": price,
                        "specs": "",
                        "url": link,
                        "year": year,
                    })
                except Exception as e:
                    logger.warning(f"eBay parse error: {e}")

        except Exception as e:
            logger.error(f"eBay scrape error: {e}")
        finally:
            await browser.close()

    return listings

def scrape_ebay(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    try:
        listings = asyncio.run(_scrape_async(min_price, max_price, min_year, radius, postcode))
    except Exception as e:
        logger.error(f"eBay scraper failed: {e}")
        listings = []
    logger.info(f"eBay: found {len(listings)} listings")
    return listings

def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
