#!/usr/bin/env python3
"""
Car Sniper Bot — Main runner
Searches AutoTrader, eBay, and Gumtree for automatic cars matching
your criteria and sends new listings to Telegram.
"""

import argparse
import concurrent.futures
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("car_sniper")

CONFIG = {
    "min_price":    int(os.environ.get("MIN_PRICE",    300)),
    "max_price":    int(os.environ.get("MAX_PRICE",    1500)),
    "min_year":     int(os.environ.get("MIN_YEAR",     2006)),
    "radius_miles": int(os.environ.get("RADIUS_MILES", 60)),
    "postcode":     os.environ.get("POSTCODE",         "LU1 1AA"),
    "location":     os.environ.get("LOCATION",         "luton"),
    "max_pages":    int(os.environ.get("MAX_PAGES",    5)),
}

SCRAPERS = {
    "autotrader": "autotrader.scrape_autotrader",
    "ebay":       "ebay.scrape_ebay",
    "gumtree":    "gumtree.scrape_gumtree",
}

SOURCE_EMOJIS = {
    "autotrader": "🚗",
    "ebay":       "🛒",
    "gumtree":    "🌳",
}


def _run_scraper(source: str) -> tuple[str, list[dict]]:
    """Import and run a single scraper; returns (source, listings)."""
    module_name, func_name = SCRAPERS[source].split(".")
    try:
        import importlib
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        kwargs = dict(
            min_price=CONFIG["min_price"],
            max_price=CONFIG["max_price"],
            min_year=CONFIG["min_year"],
            radius=CONFIG["radius_miles"],
            postcode=CONFIG["postcode"],
        )
        if source == "gumtree":
            kwargs["location"] = CONFIG["location"]
        kwargs["max_pages"] = CONFIG["max_pages"]
        results = func(**kwargs)
        return source, results
    except Exception as exc:
        logger.error(f"{source} scraper failed: {exc}", exc_info=True)
        return source, []


def run_scrapers(sources: list[str]) -> list[dict]:
    """Run scrapers concurrently and combine results."""
    all_listings: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = {pool.submit(_run_scraper, s): s for s in sources}
        for future in concurrent.futures.as_completed(futures):
            source, results = future.result()
            emoji = SOURCE_EMOJIS.get(source, "🚙")
            logger.info(f"{emoji} {source.capitalize()}: {len(results)} listing(s)")
            all_listings.extend(results)
    return all_listings


def main() -> None:
    parser = argparse.ArgumentParser(description="Car Sniper Bot")
    parser.add_argument(
        "--sources", nargs="+",
        default=list(SCRAPERS.keys()),
        choices=list(SCRAPERS.keys()),
        help="Which sources to scrape (default: all)",
    )
    parser.add_argument(
        "--test-telegram", action="store_true",
        help="Send a test message to Telegram and exit",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scrape but don't send notifications",
    )
    parser.add_argument(
        "--no-empty-summary", action="store_true",
        help="Don't send a Telegram message when no new listings are found",
    )
    parser.add_argument(
        "--clear-store", action="store_true",
        help="Wipe the seen-listings store before running",
    )
    args = parser.parse_args()

    if args.test_telegram:
        from notifier import test_telegram
        test_telegram()
        return

    logger.info("=" * 60)
    logger.info("🚗 Car Sniper Bot starting")
    logger.info(
        f"  Criteria : £{CONFIG['min_price']}–£{CONFIG['max_price']} | "
        f"{CONFIG['min_year']}+ | Auto | {CONFIG['radius_miles']} mi of {CONFIG['postcode']}"
    )
    logger.info(f"  Sources  : {', '.join(args.sources)}")
    logger.info("=" * 60)

    from store import filter_new_listings, get_stats, clear_store

    if args.clear_store:
        clear_store()
        logger.info("Store cleared.")

    # 1. Scrape
    all_listings = run_scrapers(args.sources)
    logger.info(f"Total raw listings: {len(all_listings)}")

    # 2. Deduplicate
    new_listings = filter_new_listings(all_listings)
    logger.info(f"New listings (not seen before): {len(new_listings)}")
    logger.info(f"Store stats: {get_stats()}")

    # 3. Notify
    if args.dry_run:
        logger.info("[DRY RUN] Would send the following:")
        for l in new_listings:
            logger.info(f"  [{l['source']}] {l['title']} — £{l.get('price', '?')} — {l.get('url', '')}")
    else:
        from notifier import send_notifications
        send_notifications(new_listings, send_empty_summary=not args.no_empty_summary)

    logger.info("Done ✓")


if __name__ == "__main__":
    main()
