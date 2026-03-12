"""
eBay Motors scraper using cloudscraper.
"""
import time
import logging
import re

logger = logging.getLogger(__name__)

def scrape_ebay(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    try:
        import cloudscraper
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("cloudscraper not installed")
        return []

    listings = []
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    page = 1

    while True:
        url = (
            "https://www.ebay.co.uk/sch/i.html"
            f"?_sacat=9801&_udlo={min_price}&_udhi={max_price}"
            f"&_fpos={postcode.replace(' ', '+')}&_fsradm={radius}"
            f"&LH_ItemCondition=3000&_pgn={page}&_ipg=60"
            f"&Cars_Transmission=Automatic&_sop=10"
        )

        try:
            resp = scraper.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"eBay request failed (page {page}): {e}")
            break

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("li.s-item")

        if not items:
            logger.info(f"eBay: no more results at page {page}")
            break

        found_any = False
        for item in items:
            try:
                title_el = item.select_one(".s-item__title")
                price_el = item.select_one(".s-item__price")
                link_el = item.select_one("a.s-item__link")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title or title.lower() == "shop on ebay":
                    continue

                price_raw = (price_el.get_text(strip=True) if price_el else "0").split(" to ")[0]
                digits = ''.join(filter(str.isdigit, price_raw.split(".")[0]))
                price = int(digits) if digits else 0

                link = link_el["href"] if link_el else ""
                if not link:
                    continue

                year = _extract_year(title)
                if year and year < min_year:
                    continue

                lid = link.split("/itm/")[-1].split("?")[0] if "/itm/" in link else link[-20:]
                found_any = True
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

        if not found_any or page >= 5:
            break

        next_btn = soup.select_one("a.pagination__next") or soup.select_one("[aria-label='Next page']")
        if not next_btn:
            break
        page += 1
        time.sleep(2)

    logger.info(f"eBay: found {len(listings)} listings")
    return listings

def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
