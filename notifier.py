"""
Telegram notification sender for car listings
"""
import asyncio
import logging
import os
from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def format_listing(listing: dict) -> str:
    """Format a car listing into a readable Telegram message"""
    source = listing.get("source", "Unknown")
    title = listing.get("title", "Unknown Car")
    price = listing.get("price", 0)
    specs = listing.get("specs", "")
    url = listing.get("url", "")
    year = listing.get("year", "")

    source_emoji = {
        "AutoTrader": "🚗",
        "eBay": "🛒",
        "Gumtree": "🌳",
        "Facebook Marketplace": "📘",
    }.get(source, "🚙")

    price_str = f"£{price:,}" if price else "Price unknown"
    year_str = f" • {year}" if year else ""
    specs_str = f"\n📋 {specs[:100]}" if specs else ""

    return (
        f"{source_emoji} *{source}*\n"
        f"🏷️ *{title}*\n"
        f"💰 {price_str}{year_str}"
        f"{specs_str}\n"
        f"🔗 [View Listing]({url})"
    )


async def _send_messages(listings: list[dict], is_summary: bool = False):
    """Send Telegram messages for new listings"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return

    bot = Bot(token=TELEGRAM_TOKEN)

    if is_summary and not listings:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="✅ Car scraper ran — no *new* listings found this time.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if listings:
        count = len(listings)
        header = f"🔔 *{count} new car listing{'s' if count > 1 else ''} found!*\n_(Auto • £300–£1500 • 2006+ • 60mi of Luton)_"
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=header,
            parse_mode=ParseMode.MARKDOWN,
        )

    for listing in listings:
        try:
            msg = format_listing(listing)
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False,
            )
            await asyncio.sleep(0.5)  # Avoid rate limiting
        except Exception as e:
            logger.error(f"Failed to send Telegram message for {listing.get('id')}: {e}")


def send_notifications(listings: list[dict], send_empty_summary: bool = True):
    """Send Telegram notifications for new listings (sync wrapper)"""
    try:
        asyncio.run(_send_messages(listings, is_summary=send_empty_summary))
        logger.info(f"Sent {len(listings)} Telegram notifications")
    except Exception as e:
        logger.error(f"Telegram notification error: {e}")


async def _test_connection():
    bot = Bot(token=TELEGRAM_TOKEN)
    me = await bot.get_me()
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text="✅ *Car Scraper Bot connected!*\nYou'll receive notifications here when new listings are found.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return me.username


def test_telegram():
    """Test Telegram connection"""
    username = asyncio.run(_test_connection())
    print(f"Connected as @{username}")
