"""
Facebook Marketplace scraper using Playwright with login support.
"""
import asyncio
import logging
import re
import os
import json

logger = logging.getLogger(__name__)

LUTON_LAT = 51.8787
LUTON_LON = -0.4200
FB_EMAIL = os.environ.get("FACEBOOK_EMAIL", "")
FB_PASSWORD = os.environ.get("FACEBOOK_PASSWORD", "")
SESSION_FILE = os.environ.get("FB_SESSION_FILE", "fb_session.json")

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage", "--disable-gpu",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

def _session_exists():
    return os.path.exists(SESSION_FILE) and os.path.getsize(SESSION_FILE) > 100

async def _do_login(page):
    if not FB_EMAIL or not FB_PASSWORD:
        logger.warning("FB: No credentials — skipping login")
        return False
    try:
        logger.info("FB: Logging in...")
        await page.goto("https://www.facebook.com/login", timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        for sel in ["button:has-text('Accept all')", "button:has-text('Allow all cookies')"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except Exception:
                pass
        await page.fill("#email", FB_EMAIL)
        await asyncio.sleep(1)
        await page.fill("#pass", FB_PASSWORD)
        await asyncio.sleep(1)
        await page.click("[name='login']")
        await page.wait_for_url(
            lambda url: "login" not in url and "checkpoint" not in url,
            timeout=30000,
        )
        logger.info("FB: Login successful")
        return True
    except Exception as e:
        logger.error(f"FB: Login failed: {e}")
        return False

async def _scrape_fb_async(min_price=300, max_price=1500, min_year=2006, radius_km=97):
    try:
        from playwright.async_api import async_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("Playwright not installed")
        return []

    listings = []
    search_url = (
        f"https://www.facebook.com/marketplace/luton/vehicles"
        f"?minPrice={min_price}&maxPrice={max_price}&minYear={min_year}"
        f"&transmissionType=automatic&radiusKm={radius_km}"
        f"&latitude={LUTON_LAT}&longitude={LUTON_LON}&sortBy=creation_time_descend"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx_opts = dict(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-GB")

        if _session_exists():
            try:
                with open(SESSION_FILE) as f:
                    ctx_opts["storage_state"] = json.load(f)
                logger.info("FB: Loaded saved session")
            except Exception:
                pass

        context = await browser.new_context(**ctx_opts)
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            if not _session_exists() and FB_EMAIL:
                if await _do_login(page):
                    state = await context.storage_state()
                    with open(SESSION_FILE, "w") as f:
                        json.dump(state, f)

            logger.info("FB: Loading Marketplace...")
            await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            if "login" in page.url or "checkpoint" in page.url:
                logger.warning("FB: Session expired, re-logging in")
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                if await _do_login(page):
                    state = await context.storage_state()
                    with open(SESSION_FILE, "w") as f:
                        json.dump(state, f)
                    await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                    await asyncio.sleep(5)

            for sel in ["[aria-label='Close']", "button:has-text('Not now')"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

            for _ in range(6):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            soup = BeautifulSoup(await page.content(), "lxml")
            cards = soup.select("div[aria-label*='Marketplace item']") or soup.select("a[href*='/marketplace/item/']")
            logger.info(f"FB: Found {len(cards)} cards")

            seen_ids = set()
            for card in cards:
                try:
                    link_el = card if card.name == "a" else card.select_one("a[href*='/marketplace/item/']")
                    if not link_el:
                        continue
                    href = link_el.get("href", "")
                    full_url = "https://www.facebook.com" + href if href.startswith("/") else href
                    id_match = re.search(r'/item/(\d+)', full_url)
                    if not id_match:
                        continue
                    item_id = id_match.group(1)
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    texts = [el.get_text(strip=True) for el in card.select("span") if el.get_text(strip=True)]
                    price, title = 0, ""
                    for t in texts:
                        if t.startswith("£") and not price:
                            d = ''.join(filter(str.isdigit, t.split(".")[0]))
                            price = int(d) if d else 0
                        elif len(t) > 5 and not t.startswith("£") and not title:
                            title = t
                    listings.append({
                        "id": f"fb_{item_id}",
                        "source": "Facebook Marketplace",
                        "title": title or f"FB Listing {item_id}",
                        "price": price,
                        "specs": " | ".join(texts[:4]),
                        "url": full_url,
                        "year": _extract_year(" ".join(texts)),
                    })
                except Exception as e:
                    logger.warning(f"FB card parse error: {e}")

        except Exception as e:
            logger.error(f"FB scrape error: {e}")
        finally:
            await browser.close()

    logger.info(f"Facebook Marketplace: found {len(listings)} listings")
    return listings

def scrape_facebook(min_price=300, max_price=1500, min_year=2006, radius=60):
    radius_km = int(radius * 1.60934)
    try:
        return asyncio.run(_scrape_fb_async(min_price, max_price, min_year, radius_km))
    except Exception as e:
        logger.error(f"FB scraper error: {e}")
        return []

def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
