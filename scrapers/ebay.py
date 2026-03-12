"""
eBay Motors scraper using Playwright headless browser.
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
        f"?_sacat=9801"
        f"&_udlo={min_price}&_udhi={max_price}"
        f"&_fpos={postcode.replace(' ', '+')}&_fsradm={radius}"
        f"&LH_ItemCondition=3000"
        f"&Cars_Transmission=Automatic"
        f"&Cars_Type=Car"
        f"&_sop=10&_ipg=60"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-GB")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            page_num = 1
            while page_num <= 3:
                paged_url = url + f"&_pgn={page_num}"
                await page.goto(paged_url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                soup = BeautifulSoup(await page.content(), "lxml")
                items = soup.select("li.s-item")

                if not items:
                    logger.info(f"eBay: no results at page {page_num}")
                    break

                found_any = False
                for item in items:
                    try:
                        title_el = item.select_one(".s-item__title")
                        price_el = item.select_one(".s-item__price")
                        link_el = item.select_one("a.s-item__link")
                        subtitle_el = item.select_one(".s-item__subtitle")

                        title = title_el.get_text(strip=True) if title_el else ""
                        if not title or title.lower() == "shop on ebay":
                            continue

                        # Skip vans/trucks
                        if any(w in title.lower() for w in ["van", "transit", "sprinter", "truck", "pickup"]):
                            continue

                        price_raw = (price_el.get_text(strip=True) if price_el else "0").split(" to ")[0]
                        digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                        price = int(digits) if digits else 0

                        link = link_el["href"] if link_el else ""
                        if not link:
                            continue

                        subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""
                        year = _extract_year(title + subtitle)
                        if year and year < min_year:
                            continue

                        lid = link.split("/itm/")[-1].split("?")[0] if "/itm/" in link else link[-20:]
                        found_any = True
                        listings.append({
                            "id": f"ebay_{lid}",
                            "source": "eBay",
                            "title": title,
                            "price": price,
                            "specs": subtitle,
                            "url": link,
                            "year": year,
                        })
                    except Exception as e:
                        logger.warning(f"eBay parse error: {e}")

                if not found_any:
                    break

                next_btn = soup.select_one("a.pagination__next") or soup.select_one("[aria-label='Next page']")
                if not next_btn:
                    break
                page_num += 1
                await asyncio.sleep(2)

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
