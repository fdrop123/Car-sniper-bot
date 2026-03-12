# 🚗 Car Scraper Bot

Automatically searches **AutoTrader, eBay, Gumtree, and Facebook Marketplace** for automatic cars matching your criteria and sends new listings to **Telegram**.

**Search criteria:**
- 💰 Price: £300 – £1,500
- 📅 Year: 2006 or newer
- ⚙️ Transmission: Automatic
- 📍 Within 60 miles of Luton (LU1 1AA)

---

## 🛠️ Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/car-scraper.git
cd car-scraper
```

### 2. Create a Telegram Bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABCdef...`)
4. Start a chat with your new bot (or add it to a group)
5. Get your **Chat ID**:
   - For personal: message @userinfobot or visit `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending a message
   - For a group: add the bot to the group, send a message, check `getUpdates`

### 3. Local development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Create .env file
cp .env.example .env
# Edit .env with your Telegram token and chat ID

# Test Telegram connection
python main.py --test-telegram

# Run a dry run (no notifications sent)
python main.py --dry-run

# Run specific sources only
python main.py --sources autotrader ebay

# Full run
python main.py
```

### 4. GitHub Actions (automated)

#### Add Secrets to your GitHub repo

Go to: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID |

#### Push to GitHub

```bash
git add .
git commit -m "Initial setup"
git push origin main
```

The workflow runs automatically every **3 hours**. You can also trigger it manually from the **Actions** tab.

---

## ⚙️ Customise search parameters

Edit the defaults in the GitHub Actions workflow (`.github/workflows/scraper.yml`) under the `env:` block:

```yaml
env:
  MIN_PRICE: "300"
  MAX_PRICE: "1500"
  MIN_YEAR: "2006"
  RADIUS_MILES: "60"
  POSTCODE: "LU1 1AA"
```

Or pass them as environment variables locally in `.env`.

---

## 📁 Project structure

```
car-scraper/
├── main.py                  # Main runner
├── notifier.py              # Telegram notifications
├── store.py                 # Seen-listings deduplication
├── requirements.txt
├── .env.example
├── .github/
│   └── workflows/
│       └── scraper.yml      # GitHub Actions schedule
└── scrapers/
    ├── autotrader.py
    ├── ebay.py
    ├── gumtree.py
    └── facebook.py          # Uses Playwright (headless Chrome)
```

---

## ⚠️ Notes

- **Facebook Marketplace** requires a headless browser (Playwright/Chromium). It may be less reliable due to login walls. If FB blocks the scraper, the other three sources will still work fine — just remove `facebook` from the sources list in the workflow.
- **Rate limiting**: The bot adds delays between requests to be respectful. Don't lower these too much or you may get IP-blocked.
- **seen_listings.json** is cached between GitHub Actions runs so you won't be notified about the same listing twice. This cache persists using GitHub Actions cache (keyed by run).
- Scraping may break if sites update their HTML structure. If a source stops working, check the selectors in the relevant `scrapers/` file.
