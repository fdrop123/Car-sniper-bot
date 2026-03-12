"""
eBay scraper using RSS feed (no IP blocking) + HTML fallback.
"""
import logging
import re
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

def scrape_ebay(min_price=300, max_price=1500, min_year=2006, radius=60, postcode="LU1 1AA"):
    listings = []

    # eBay RSS feed - not blocked by IP filters
    rss_url = (
        "https://www.ebay.co.uk/sch/i.html"
        f"?_sacat=9801"
        f"&_udlo={min_price}&_udhi={max_price}"
        f"&_fpos={postcode.replace(' ', '+')}"
        f"&_fsradm={radius}"
        f"&LH_ItemCondition=3000"
        f"&Cars_Transmission=Automatic"
        f"&_rss=1"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RSS reader)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    }

    try:
        resp = requests.get(rss_url, headers=headers, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        items = root.findall(".//item")
        logger.info(f"eBay RSS: got {len(items)} items")

        for item in items:
            try:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "")

                if not title or not link:
                    continue

                # Extract price from title or description
                price_match = re.search(r'£([\d,]+)', title + desc)
                price = int(price_match.group(1).replace(",", "")) if price_match else 0

                year = _extract_year(title + desc)
                if year and year < min_year:
                    continue

                lid = link.split("/itm/")[-1].split("?")[0] if "/itm/" in link else link[-20:]

                listings.append({
                    "id": f"ebay_{lid}",
                    "source": "eBay",
                    "title": title,
                    "price": price,
                    "specs": re.sub('<[^<]+?>', '', desc)[:120],
                    "url": link,
                    "year": year,
                })
            except Exception as e:
                logger.warning(f"eBay RSS parse error: {e}")

    except Exception as e:
        logger.error(f"eBay RSS failed: {e}")
        # Fallback to cloudscraper HTML
        listings = _scrape_ebay_html(min_price, max_price, min_year, radius, postcode)

    logger.info(f"eBay: found {len(listings)} listings")
    return listings


def _scrape_ebay_html(min_price, max_price, min_year, radius, postcode):
    listings = []
    try:
        import cloudscraper
        from bs4 import BeautifulSoup
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        url = (
            "https://www.ebay.co.uk/sch/i.html"
            f"?_sacat=9801&_udlo={min_price}&_udhi={max_price}"
            f"&_fpos={postcode.replace(' ', '+')}&_fsradm={radius}"
            f"&LH_ItemCondition=3000&Cars_Transmission=Automatic"
        )
        resp = scraper.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, "lxml")
        for item in soup.select("li.s-item"):
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
                listings.append({
                    "id": f"ebay_{lid}",
                    "source": "eBay",
                    "title": title,
                    "price": price,
                    "specs": "",
                    "url": link,
                    "year": year,
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"eBay HTML fallback failed: {e}")
    return listings


def _extract_year(text):
    matches = re.findall(r'\b(20[01][0-9]|202[0-9])\b', text)
    return int(matches[0]) if matches else None
