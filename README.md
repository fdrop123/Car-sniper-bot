# 🚗 Car Sniper Bot

Automatically searches **AutoTrader**, **eBay**, and **Gumtree** for automatic cars matching your criteria and sends new listings straight to **Telegram**.

Default search criteria (all configurable via `.env` or GitHub Actions environment variables):

| Setting | Default |
|---|---|
| Price | £300 – £1,500 |
| Year | 2006 or newer |
| Transmission | Automatic |
| Radius | 60 miles of Luton (LU1 1AA) |

---

## 🛠️ Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/car-sniper-bot.git
cd car-sniper-bot
```

### 2. Create a Telegram bot

1. Message **@BotFather** on Telegram → `/newbot` → follow the prompts
2. Copy the **bot token** (e.g. `123456:ABCdef…`)
3. Start a chat with your bot (or add it to a group)
4. Get your **Chat ID** — message **@userinfobot**, or visit `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending a message

### 3. Local development

```bash
# Install dependencies (no Playwright/Chrome needed)
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# Test Telegram connection
python main.py --test-telegram

# Dry run (scrapes, but no notifications sent)
python main.py --dry-run

# Run specific sources only
python main.py --sources autotrader ebay

# Full run
python main.py
```

### 4. GitHub Actions (automated)

Add two secrets to your repo under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID |

Then push to GitHub — the workflow runs automatically every **3 hours**.  
You can also trigger it manually from the **Actions** tab, with an optional dry-run toggle.

---

## ⚙️ Customise search parameters

Edit the `env:` block in `.github/workflows/scraper.yml`:

```yaml
env:
  MIN_PRICE:    "300"
  MAX_PRICE:    "1500"
  MIN_YEAR:     "2006"
  RADIUS_MILES: "60"
  POSTCODE:     "LU1 1AA"
  LOCATION:     "luton"
  MAX_PAGES:    "5"
```

Or set them in `.env` for local runs.

---

## 📁 Project structure

```
car-sniper-bot/
├── main.py          # Orchestrator — runs scrapers concurrently, deduplicates, notifies
├── autotrader.py    # AutoTrader UK scraper
├── ebay.py          # eBay UK Motors scraper
├── gumtree.py       # Gumtree UK scraper
├── notifier.py      # Telegram notifications (MarkdownV2, rate-limit aware)
├── store.py         # Seen-listings deduplication (hash-based, auto-pruning)
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── scraper.yml
```

---

## 🖊️ Command-line options

```
usage: main.py [-h] [--sources {autotrader,ebay,gumtree} [...]]
               [--test-telegram] [--dry-run] [--no-empty-summary] [--clear-store]

  --sources           Which sources to scrape (default: all three)
  --test-telegram     Send a test message and exit
  --dry-run           Scrape but don't send notifications
  --no-empty-summary  Don't send a Telegram message when nothing new is found
  --clear-store       Wipe the seen-listings store before running
```

---

## ⚠️ Notes

- **No Playwright/Chrome required** — all three scrapers use plain HTTP requests, making the bot fast and lightweight.
- **Rate limiting** — each scraper waits ~2.5 seconds between pages. Don't lower this or you risk getting IP-blocked.
- **Seen-listings cache** is persisted between GitHub Actions runs via `actions/cache`. Entries older than 90 days are auto-pruned.
- **Selectors may break** if sites update their HTML. If a source stops working, check the relevant scraper file and update the CSS selectors.
- **Concurrent scraping** — all three sources are scraped in parallel threads for faster runs.
