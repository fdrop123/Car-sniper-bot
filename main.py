#!/usr/bin/env python3
"""
Car Scraper Bot - Main runner
Searches AutoTrader, eBay, Gumtree, and Facebook Marketplace
for automatic cars £300-£1500, 2006+, within 60 miles of Luton.
Sends new listings to Telegram.
"""
import logging
import os
import sys
import argparse
from dotenv import load_dotenv

# Load .env if present (local development)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("car_scraper")

# Search parameters
CONFIG = {
    "min_price": int(os.environ.get("MIN_PRICE", 300)),
    "max_price": int(os.environ.get("MAX_PRICE", 1500)),
    "min_year": int(os.environ.get("MIN_YEAR", 2006)),
    "radius_miles": int(os.environ.get("RADIUS_MILES", 60)),
    "postcode": os.environ.get("POSTCODE", "LU1 1AA"),
    "location": os.environ.get("LOCATION", "luton"),
}


def run_scrapers(sources: list[str]) -> list[dict]:
    """Run all enabled scrapers and return combined listings"""
    all_listings = []

    if "autotrader" in sources:
        logger.info("Scraping AutoTrader...")
        try:
            from scrapers.autotrader import scrape_autotrader
            results = scrape_autotrader(
                min_price=CONFIG["min_price"],
                max_price=CONFIG["max_price"],
                min_year=CONFIG["min_year"],
                radius=CONFIG["radius_miles"],
                postcode=CONFIG["postcode"],
            )
            all_listings.extend(results)
            logger.info(f"AutoTrader: {len(results)} listings")
        except Exception as e:
            logger.error(f"AutoTrader scraper failed: {e}")

    if "ebay" in sources:
        logger.info("Scraping eBay...")
        try:
            from scrapers.ebay import scrape_ebay
            results = scrape_ebay(
                min_price=CONFIG["min_price"],
                max_price=CONFIG["max_price"],
                min_year=CONFIG["min_year"],
                radius=CONFIG["radius_miles"],
                postcode=CONFIG["postcode"],
            )
            all_listings.extend(results)
            logger.info(f"eBay: {len(results)} listings")
        except Exception as e:
            logger.error(f"eBay scraper failed: {e}")

    if "gumtree" in sources:
        logger.info("Scraping Gumtree...")
        try:
            from scrapers.gumtree import scrape_gumtree
            results = scrape_gumtree(
                min_price=CONFIG["min_price"],
                max_price=CONFIG["max_price"],
                min_year=CONFIG["min_year"],
                radius=CONFIG["radius_miles"],
                location=CONFIG["location"],
            )
            all_listings.extend(results)
            logger.info(f"Gumtree: {len(results)} listings")
        except Exception as e:
            logger.error(f"Gumtree scraper failed: {e}")

    if "facebook" in sources:
        logger.info("Scraping Facebook Marketplace...")
        try:
            from scrapers.facebook import scrape_facebook
            results = scrape_facebook(
                min_price=CONFIG["min_price"],
                max_price=CONFIG["max_price"],
                min_year=CONFIG["min_year"],
                radius=CONFIG["radius_miles"],
            )
            all_listings.extend(results)
            logger.info(f"Facebook Marketplace: {len(results)} listings")
        except Exception as e:
            logger.error(f"Facebook scraper failed: {e}")

    return all_listings


def main():
    parser = argparse.ArgumentParser(description="Car scraper bot")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["autotrader", "ebay", "gumtree", "facebook"],
        choices=["autotrader", "ebay", "gumtree", "facebook"],
        help="Which sources to scrape",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Test Telegram connection and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape but don't send notifications",
    )
    parser.add_argument(
        "--no-empty-summary",
        action="store_true",
        help="Don't send a message if no new listings found",
    )
    args = parser.parse_args()

    if args.test_telegram:
        from notifier import test_telegram
        test_telegram()
        return

    logger.info("=" * 60)
    logger.info("Car Scraper Bot starting")
    logger.info(f"Search: £{CONFIG['min_price']}–£{CONFIG['max_price']} | "
                f"{CONFIG['min_year']}+ | Auto | {CONFIG['radius_miles']}mi of {CONFIG['postcode']}")
    logger.info(f"Sources: {', '.join(args.sources)}")
    logger.info("=" * 60)

    # 1. Scrape all sources
    all_listings = run_scrapers(args.sources)
    logger.info(f"Total raw listings: {len(all_listings)}")

    # 2. Filter out already-seen listings
    from store import filter_new_listings, get_stats
    new_listings = filter_new_listings(all_listings)
    logger.info(f"New listings: {len(new_listings)}")

    stats = get_stats()
    logger.info(f"DB stats: {stats}")

    # 3. Send notifications
    if not args.dry_run:
        from notifier import send_notifications
        send_notifications(
            new_listings,
            send_empty_summary=not args.no_empty_summary,
        )
    else:
        logger.info("[DRY RUN] Would send notifications for:")
        for listing in new_listings:
            logger.info(f"  [{listing['source']}] {listing['title']} — £{listing.get('price', '?')}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
