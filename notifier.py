"""
Telegram notification sender for Car Sniper Bot.

Formats listings into clean, readable messages and sends them via the
python-telegram-bot library. Handles Telegram rate limits automatically.
"""

import asyncio
import logging
import os
import time

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SOURCE_EMOJI = {
    "autotrader": "🚗",
    "ebay":       "🛒",
    "gumtree":    "🌳",
}

SOURCE_LABEL = {
    "autotrader": "AutoTrader",
    "ebay":       "eBay",
    "gumtree":    "Gumtree",
}


def _escape(text: str) -> str:
    """Escape characters that have special meaning in Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def format_listing(listing: dict) -> str:
    """Format a single car listing into a Telegram MarkdownV2 message."""
    source  = listing.get("source", "unknown")
    title   = listing.get("title", "Unknown Car")
    price   = listing.get("price")
    year    = listing.get("year")
    mileage = listing.get("mileage")
    loc     = listing.get("location")
    url     = listing.get("url", "")

    emoji = SOURCE_EMOJI.get(source, "🚙")
    label = SOURCE_LABEL.get(source, source.capitalize())

    price_str   = f"£{price:,}" if price else "Price not listed"
    year_str    = f"  •  {year}" if year else ""
    mileage_str = f"  •  {mileage}" if mileage else ""
    loc_str     = f"\n📍 {_escape(loc)}" if loc else ""

    lines = [
        f"{emoji} *{_escape(label)}*",
        f"🏷️ *{_escape(title)}*",
        f"💰 {_escape(price_str)}{_escape(year_str)}{_escape(mileage_str)}",
    ]
    if loc_str:
        lines.append(loc_str)
    lines.append(f"🔗 [View listing]({url})")

    return "\n".join(lines)


async def _send(bot: Bot, text: str) -> None:
    """Send a Telegram message with automatic retry on rate limit."""
    for attempt in range(4):
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=False,
            )
            return
        except RetryAfter as exc:
            wait = exc.retry_after + 1
            logger.warning(f"Telegram rate limit — waiting {wait}s")
            await asyncio.sleep(wait)
        except TelegramError as exc:
            logger.error(f"Telegram error (attempt {attempt + 1}): {exc}")
            if attempt < 3:
                await asyncio.sleep(3)


async def _run_notifications(listings: list[dict], send_empty_summary: bool) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variable not set")
        return

    bot = Bot(token=TELEGRAM_TOKEN)

    if not listings:
        if send_empty_summary:
            await _send(
                bot,
                "✅ *Car Sniper ran* — no new listings this time\\.",
            )
        return

    count = len(listings)
    plural = "s" if count != 1 else ""
    header = (
        f"🔔 *{count} new listing{plural} found\\!*\n"
        f"_Auto · £300–£1,500 · 2006\\+ · 60 mi of Luton_"
    )
    await _send(bot, header)

    # Group by source for a quick summary
    by_source: dict[str, int] = {}
    for l in listings:
        by_source[l.get("source", "?")] = by_source.get(l.get("source", "?"), 0) + 1

    # Send individual listings
    for listing in listings:
        try:
            msg = format_listing(listing)
            await _send(bot, msg)
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.error(f"Failed to format/send listing {listing.get('id')}: {exc}")

    # Footer summary
    summary_parts = [
        f"{SOURCE_EMOJI.get(src, '🚙')} {SOURCE_LABEL.get(src, src)}: {n}"
        for src, n in sorted(by_source.items())
    ]
    footer = "📊 *Breakdown:*\n" + "\n".join(_escape(p) for p in summary_parts)
    await _send(bot, footer)


def send_notifications(listings: list[dict], send_empty_summary: bool = True) -> None:
    """Synchronous entry point for sending Telegram notifications."""
    try:
        asyncio.run(_run_notifications(listings, send_empty_summary))
        logger.info(f"Telegram: sent notifications for {len(listings)} listing(s)")
    except Exception as exc:
        logger.error(f"Telegram notification run failed: {exc}", exc_info=True)


async def _test() -> str:
    bot = Bot(token=TELEGRAM_TOKEN)
    me = await bot.get_me()
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=(
            "✅ *Car Sniper Bot connected\\!*\n"
            "You'll receive notifications here when new listings match your criteria\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return me.username


def test_telegram() -> None:
    """Send a test message to verify the Telegram connection."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        return
    username = asyncio.run(_test())
    print(f"✅ Connected as @{username} — check your Telegram for the confirmation message.")
