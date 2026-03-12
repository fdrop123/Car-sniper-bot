"""
Facebook Marketplace scraper using Playwright (headless browser)
Supports FB login via FACEBOOK_EMAIL / FACEBOOK_PASSWORD env vars.
Saves a browser session (cookies + storage) so login only happens once,
reducing the chance of 2FA prompts or bot detection on repeat runs.
"""
import asyncio
import logging
import re
import os
import json

logger = logging.getLogger(__name__)

# Luton lat/lon for FB Marketplace radius search
LUTON_LAT = 51.8787
LUTON_LON = -0.4200

FB_EMAIL = os.environ.get("FACEBOOK_EMAIL", "")
FB_PASSWORD = os.environ.get("FACEBOOK_PASSWORD", "")

# Session state file — persisted between GitHub Actions runs via cache
SESSION_FILE = os.environ.get("FB_SESSION_FILE", "fb_session.json")

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def _session_exists() -> bool:
    return os.path.exists(SESSION_FILE) and os.path.getsize(SESSION_FILE) > 100


async def _do_login(page) -> bool:
    """Attempt to log in to Facebook. Returns True on success."""
    if not FB_EMAIL or not FB_PASSWORD:
        logger.warning("FB: No credentials provided — scraping without login")
        return False

    logger.info("FB: Attempting login...")
    try:
        await page.goto("https://www.facebook.com/login", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Accept cookies if prompted
        for selector in [
            "button:has-text('Accept all')",
            "button:has-text('Allow all cookies')",
            "[data-testid='cookie-policy-manage-dialog-accept-button']",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except Exception:
                pass

        # Fill login form
        await page.fill("#email", FB_EMAIL)
        await asyncio.sleep(0.8)
        await page.fill("#pass", FB_PASSWORD)
        await asyncio.sleep(0.8)
        await page.click("[name='login']")

        # Wait for redirect away from login page
        await page.wait_for_url(
            lambda url: "login" not in url and "checkpoint" not in url,
            timeout=15000,
        )

        logged_in = await page.locator("[aria-label='Facebook']").is_visible(timeout=5000)
        if logged_in:
            logger.info("FB: Login successful")
            return True
        else:
            logger.warning("FB: Login may have failed — checkpoint or 2FA required?")
            return False

    except Exception as e:
        logger.error(f"FB: Login failed: {e}")
        return False


async def _scrape_fb_async(min_price=300, max_price=1500, min_year=2006, radius_km=97):
    """Async FB Marketplace scraper with login and session persistence"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: playwright install chromium")
        return []

    listings = []

    search_url = (
        f"https://www.facebook.com/marketplace/luton/vehicles"
        f"?minPrice={min_price}"
        f"&maxPrice={max_price}"
        f"&minYear={min_year}"
        f"&transmissionType=automatic"
        f"&radiusKm={radius_km}"
        f"&latitude={LUTON_LAT}"
        f"&longitude={LUTON_LON}"
        f"&sortBy=creation_time_descend"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)

        # ── Load saved session if available ──────────────────────────
        context_options = dict(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
        )
        if _session_exists():
            logger.info("FB: Loading saved browser session")
            try:
                with open(SESSION_FILE, "r") as f:
                    context_options["storage_state"] = json.load(f)
            except Exception as e:
                logger.warning(f"FB: Could not load session: {e}")

        context = await browser.new_context(**context_options)
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2,woff}", lambda r: r.abort())

        try:
            # ── Login if no session on disk ───────────────────────────
            if not _session_exists() and FB_EMAIL:
                logged_in = await _do_login(page)
                if logged_in:
                    state = await context.storage_state()
                    with open(SESSION_FILE, "w") as f:
                        json.dump(state, f)
                    logger.info(f"FB: Session saved to {SESSION_FILE}")

            # ── Navigate to Marketplace search ────────────────────────
            logger.info("FB: Loading Marketplace search...")
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            # If we hit a login wall, session expired — retry login
            if "login" in page.url or "checkpoint" in page.url:
                logger.warning("FB: Session expired — re-logging in")
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                logged_in = await _do_login(page)
                if logged_in:
                    state = await context.storage_state()
                    with open(SESSION_FILE, "w") as f:
                        json.dump(state, f)
                    await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                    await asyncio.sleep(4)

            # Dismiss popups
            for selector in [
                "[aria-label='Close']",
                "div[role='dialog'] button:has-text('Not now')",
                "button:has-text('Not now')",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await asyncio.sleep(0.8)
                except Exception:
                    pass

            # Scroll to load more listings
            for i in range(6):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            # ── Parse listings ────────────────────────────────────────
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(await page.content(), "lxml")

            cards = soup.select("div[aria-label*='Marketplace item']") or \
                    soup.select("a[href*='/marketplace/item/']")

            logger.info(f"FB: Found {len(cards)} raw cards")
            seen_ids: set = set()

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
                            digits = ''.join(filter(str.isdigit, t.split(".")[0]))
                            price = int(digits) if digits else 0
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
                    logger.warning(f"FB: Failed to parse card: {e}")

        except Exception as e:
            logger.error(f"FB Marketplace scrape failed: {e}")
        finally:
            await browser.close()

    logger.info(f"Facebook Marketplace: found {len(listings)} listings")
    return listings


def scrape_facebook(min_price=300, max_price=1500, min_year=2006, radius=60):
    """Synchronous wrapper for FB Marketplace scraper"""
    radius_km = int(radius * 1.60934)
    try:
        return asyncio.run(_scrape_fb_async(min_price, max_price, min_year, radius_km))
    except Exception as e:
        logger.error(f"FB scraper error: {e}")
        return []


def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
