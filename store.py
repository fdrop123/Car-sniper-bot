"""
Seen-listings store.

Persists a set of listing IDs to a local JSON file so the bot never
notifies you about the same listing twice across runs.

The store also tracks when each listing was first seen, which lets you
prune very old entries to stop the file growing indefinitely.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

STORE_PATH = os.environ.get("STORE_PATH", "seen_listings.json")
MAX_AGE_DAYS = int(os.environ.get("STORE_MAX_AGE_DAYS", 90))


def _load() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Support legacy format (plain set saved as list)
            if isinstance(data, list):
                return {item: None for item in data}
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load store from {STORE_PATH}: {exc}. Starting fresh.")
        return {}


def _save(store: dict) -> None:
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except OSError as exc:
        logger.error(f"Could not save store to {STORE_PATH}: {exc}")


def _listing_key(listing: dict) -> str:
    """
    Return a stable, unique key for a listing.
    Prefers the explicit `id` field; falls back to a hash of (source, url).
    """
    lid = listing.get("id")
    if lid:
        return str(lid)
    fingerprint = f"{listing.get('source', '')}|{listing.get('url', '')}|{listing.get('title', '')}"
    return "hash_" + hashlib.sha1(fingerprint.encode()).hexdigest()[:16]


def _prune(store: dict) -> dict:
    """Remove entries older than MAX_AGE_DAYS."""
    if MAX_AGE_DAYS <= 0:
        return store
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    pruned = {
        k: v for k, v in store.items()
        if v is None or datetime.fromisoformat(v) >= cutoff
    }
    removed = len(store) - len(pruned)
    if removed:
        logger.debug(f"Pruned {removed} old entries from store.")
    return pruned


def filter_new_listings(listings: list[dict]) -> list[dict]:
    """
    Return only listings not previously seen, and mark the new ones as seen.
    Deduplicates within the current batch too.
    """
    store = _prune(_load())
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    new: list[dict] = []
    seen_this_run: set[str] = set()

    for listing in listings:
        key = _listing_key(listing)
        if key in store or key in seen_this_run:
            continue
        seen_this_run.add(key)
        store[key] = now_iso
        new.append(listing)

    _save(store)
    return new


def get_stats() -> dict:
    """Return basic stats about the store."""
    store = _load()
    return {
        "total_seen": len(store),
        "store_path": STORE_PATH,
    }


def clear_store() -> None:
    """Wipe the seen-listings store completely."""
    _save({})
    logger.info(f"Store cleared: {STORE_PATH}")
