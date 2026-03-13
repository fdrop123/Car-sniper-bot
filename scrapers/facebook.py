"""
Facebook Marketplace scraper.
- Logs in once and saves session
- Reuses session on subsequent runs
- Only re-logs in if session is older than 20 hours or invalid
"""
import asyncio
import logging
import re
import os
import json
import time

logger = logging.getLogger(__name__)

LUTON_LAT = 51.8787
LUTON_LON = -0.4200
FB_EMAIL = os.environ.get("FACEBOOK_EMAIL", "")
FB_PASSWORD = os.environ.get("FACEBOOK_PASSWORD", "")
SESSION_FILE = os.environ.get("FB_SESSION_FILE", "fb_session.json")
SESSION_MAX_AGE_HOURS = 20

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage", "--disable-gpu",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

def _session_valid():
    if not os.path.exists(SESSION_FILE):
        return False
    if os.path.getsize(SESSION_FILE) < 100:
        return False
    age_hours = (time.time() - os.path.getmtime(SESSION_FILE)) / 3600
    if age_hours > SESSION_MAX_AGE_HOURS:
        logger.info(f"FB: Session is {age_hours:.1f} hours old - will re-login")
        return False
    logger.info(f"FB: Session is {age_hours:.1f} hours old - reusing")
    return True

def _is_bad_url(url):
    return any(x in url for x in ["login", "checkpoint", "two_step_verification", "verify"])

async def _do_login(browser):
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800},
        locale="en-GB",
    )
    page = await context.new_page()
    try:
        logger.info("FB: Logging in (once per 20 hours)...")
        await page.goto("https://www.facebook.com", timeout=60000, wait_until="networkidle")
        await asyncio.sleep(4)

        for sel in ["button:has-text('Accept all')", "button:has-text('Allow all cookies')"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(2)
                    break
            except Exception:
                pass

        try:
            await page.wait_for_selector("input[name='email']", timeout=15000)
        except Exception:
            logger.error("FB: Login form not found")
            await page.screenshot(path="debug_fb_login.png")
            await context.close()
            return None

        await page.fill("input[name='email']", FB_EMAIL)
        await asyncio.sleep(1)
        await page.fill("input[name='pass']", FB_PASSWORD)
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(10)

        current_url = page.url
        logger.info(f"FB: After login URL = {current_url}")

        if _is_bad_url(current_url):
            logger.warning("FB: Login blocked by Facebook security check - only works from home IP")
            await page.screenshot(path="debug_fb_login.png")
            await context.close()
            return None

        logger.info("FB: Login successful! Session saved for 20 hours.")
        state = await context.storage_state()
        with open(SESSION_FILE, "w") as f:
            json.dump(state, f)
        await context.close()
        return state

    except Exception as e:
        logger.error(f"FB: Login error: {e}")
        try:
            await page.screenshot(path="debug_fb_login.png")
        except Exception:
            pass
        await context.close()
        return None

async def _scrape_fb_async(min_price=300, max_price=1500, min_year=2006, radius_km=97):
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    listings = []

    search_url = (
        f"https://www.facebook.com/marketplace/luton/vehicles"
        f"?minPrice={min_price}&maxPrice={max_price}&minYear={min_year}"
        f"&transmissionType=automatic&radiusKm={radius_km}"
        f"&latitude={LUTON_LAT}&longitude={LUTON_LON}&sortBy=creation_time_descend"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)

        storage_state = None
        if _session_valid():
            try:
                with open(SESSION_FILE) as f:
                    storage_state = json.load(f)
            except Exception:
                pass

        if not storage_state and FB_EMAIL:
            storage_state = await _do_login(browser)

        if not storage_state:
            logger.warning("FB: No valid session - skipping Facebook this run")
            await browser.close()
            return []

        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            storage_state=storage_state,
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,woff2}", lambda r: r.abort())

        try:
            logger.info("FB: Loading Marketplace...")
            await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(8)

            logger.info(f"FB: URL={page.url}")

            if _is_bad_url(page.url):
                logger.warning("FB: Session expired - will re-login next run")
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                await browser.close()
                return []

            for sel in ["[aria-label='Close']", "button:has-text('Not now')"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

            for _ in range(8):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            soup = BeautifulSoup(await page.content(), "lxml")
            cards = (
                soup.select("div[aria-label*='Marketplace item']") or
                soup.select("a[href*='/marketplace/item/']")
            )
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
