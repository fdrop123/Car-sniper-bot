"""
Persistent store for seen listing IDs to avoid duplicate notifications.
Uses a JSON file (seen_listings.json) so it works with GitHub Actions artifacts.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("SEEN_DB_PATH", "seen_listings.json")


def load_seen() -> dict:
    """Load the set of seen listing IDs from disk"""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load seen DB: {e}")
    return {}


def save_seen(seen: dict):
    """Save seen listing IDs to disk"""
    try:
        with open(DB_PATH, "w") as f:
            json.dump(seen, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save seen DB: {e}")


def filter_new_listings(listings: list[dict]) -> list[dict]:
    """Return only listings not previously seen, and update the store"""
    seen = load_seen()
    new_listings = []

    for listing in listings:
        lid = listing.get("id")
        if not lid:
            continue
        if lid not in seen:
            new_listings.append(listing)
            seen[lid] = {
                "first_seen": datetime.utcnow().isoformat(),
                "title": listing.get("title", ""),
                "price": listing.get("price", 0),
                "source": listing.get("source", ""),
            }

    save_seen(seen)
    logger.info(f"Filter: {len(listings)} total → {len(new_listings)} new")
    return new_listings


def get_stats() -> dict:
    """Return stats about tracked listings"""
    seen = load_seen()
    by_source = {}
    for v in seen.values():
        src = v.get("source", "Unknown")
        by_source[src] = by_source.get(src, 0) + 1
    return {"total_seen": len(seen), "by_source": by_source}
