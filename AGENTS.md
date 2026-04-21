# CS2 Marketplace Bot — Agent Guide

## Project Overview

This is a **Telegram Bot + WebApp** for a CS2 (Counter-Strike 2) skin marketplace. Users can browse, purchase, and receive CS2 skins through a Telegram WebApp interface, with payments processed via Telegram Stars.

The bot integrates with the **XPANDA P2P API** (p2p.xpanda.pro) for inventory management and Steam trade offer automation.

### Key Features
- **Marketplace**: Browse and search CS2 skins with real-time prices
- **Payment**: Purchase via Telegram Stars (XTR currency)
- **Referral System**: Users get a free random skin for inviting friends (configurable threshold)
- **Gift Cases**: Animated case opening for referral rewards
- **Steam Integration**: Automatic trade offer delivery after purchase

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11 |
| Bot Framework | aiogram 3.13.1 |
| Web Framework | FastAPI 0.115.0 |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) + asyncpg |
| HTTP Client | aiohttp 3.10.5 |
| Server | uvicorn 0.30.6 |
| Frontend | Vanilla JS + Telegram WebApp SDK |
| Deployment | Docker, Railway |

---

## Project Structure

```
cs2_market_bot/
├── main.py                    # Entry point: init DB, start uvicorn
├── bot.py                     # Telegram Bot setup (Bot, Dispatcher)
├── app.py                     # FastAPI: webhooks, REST API endpoints
├── handlers.py                # Telegram command handlers (/start, /bind, /broadcast)
├── database.py                # SQLAlchemy models + async DB operations
├── cache.py                   # Singleton item cache with XPANDA sync
├── keyboards.py               # Telegram inline keyboards (WebApp buttons)
├── config.py                  # Configuration constants
├── requirements.txt           # Python dependencies
├── docker-compose.yml         # Docker orchestration
├── Dockerfile                 # Container build
├── .env                       # Environment variables (gitignored)
├── .env.example               # Environment template
├── web_app/                   # Telegram WebApp static files
│   ├── index.html             # WebApp UI (landing, marketplace, profile)
│   └── app.js                 # WebApp logic + Telegram JS SDK
├── data/                      # Static item images data
│   ├── skins.json
│   ├── crates.json
│   └── stickers.json
└── xpanda_fetch_all_items.py  # Utility: fetch all items from XPANDA
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
BOT_TOKEN=your_telegram_bot_token
XPANDA_API_KEY=your_xpanda_api_key
XPANDA_SECRET=your_xpanda_secret_for_signing
WEBHOOK_SECRET=long_random_secret_for_webhook_security
RAILWAY_PUBLIC_DOMAIN=your-app.railway.app  # Auto-set on Railway
PORT=8000                                   # Railway uses this
CACHE_UPDATE_INTERVAL=300                   # Seconds between cache updates
DOLAR_TO_STARS=45                           # Conversion rate for pricing
CHEAP_ITEMS_COUNT=5                         # Number of cheap items for gifts
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
OWNER_ID=123456789                          # Admin Telegram ID for notifications
```

---

## Build and Run Commands

### Local Development (without Docker)

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env file
copy .env.example .env
# Edit .env with your values

# 4. Run the application
python main.py
```

### Docker Deployment

```bash
# Build and run
docker-compose up --build -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose down
```

---

## Architecture Details

### 1. FastAPI Application (`app.py`)

- **Webhook endpoint** (`POST /webhook`): Receives Telegram updates with secret token validation
- **REST API** for WebApp:
  - `GET /api/profile/{telegram_id}` — User profile data
  - `POST /api/bind/{telegram_id}` — Bind Steam trade link
  - `GET /api/items` — Paginated item list with search
  - `GET /api/balance` — XPANDA balance info
  - `GET /api/item_price` — Fresh price for specific item
  - `POST /api/create_invoice` — Create Telegram Stars invoice
  - `POST /api/claim_gift/{user_id}` — Process referral gift
- **Static files**: Serves `web_app/` directory at `/web_app`

### 2. Telegram Bot (`bot.py`, `handlers.py`)

Commands:
- `/start [ref_id]` — Register user, process referrals
- `/bind <profile> <trade_link>` — Bind Steam (legacy)
- `/broadcast <text>` — Admin: broadcast to all users (OWNER_ID only)

Handlers:
- `pre_checkout_query` — Confirm all payments
- `successful_payment` — Process purchase, create XPANDA deal
- `claim_gift` callback — Activate gift case

### 3. Database (`database.py`)

PostgreSQL with SQLAlchemy ORM (async).

**User model:**
- `telegram_id` (BigInteger, PK)
- `referred_by` (BigInteger, FK) — Who invited this user
- `referrals` (Integer) — Count of invited users
- `steam_profile` (String) — Steam profile URL
- `trade_link` (String) — Steam trade offer URL
- `has_gift` (Boolean) — Has unclaimed gift
- `gift_item` (String) — Reserved gift item (optional)

### 4. Cache (`cache.py`)

Singleton pattern (`ItemsCache`) that:
- Polls XPANDA API every `CACHE_UPDATE_INTERVAL` seconds
- Fetches item prices, quantities
- Loads images from local JSON files (`data/*.json`)
- Updates balance information
- Converts RUB prices to Telegram Stars

### 5. WebApp (`web_app/`)

Three-tab interface:
1. **Landing**: Referral link, falling skins animation, case roll animation
2. **Marketplace**: Searchable item grid with purchase buttons
3. **Profile**: Referral count, Steam trade link binding

Purchase flow:
1. Check trade link is bound
2. Check XPANDA balance covers price
3. Fetch fresh price from API
4. Create Telegram invoice
5. On payment → WebApp calls `webApp.openInvoice()`

---

## Code Style Guidelines

1. **Language**: Comments and strings in Russian (user-facing), code in English
2. **Async/Await**: All I/O operations use `async`/`await` (aiogram, aiohttp, SQLAlchemy async)
3. **Type Hints**: Use Python 3.9+ type hints (`list[User]`, `User | None`)
4. **Error Handling**: Wrap external API calls in try/except, notify OWNER_ID on critical errors
5. **Logging**: Use `print()` for debug logs, bot messages to OWNER_ID for production alerts

---

## Security Considerations

1. **Webhook Secret**: Always validate `X-Telegram-Bot-Api-Secret-Token` header
2. **HMAC Signatures**: XPANDA purchases use HMAC-SHA256 signing with `XPANDA_SECRET`
3. **Environment Variables**: Never commit `.env` or API keys
4. **Trade Link Validation**: Regex validation in both frontend (`app.js`) and backend
5. **Cooldowns**: 60-second cooldown per item ID for invoice creation (prevents double-spending)
6. **Price Validation**: Fresh price check before purchase, max 20% tolerance

---

## Testing

```bash
# Manual purchase test (edit values in file first)
python test.py

# Fetch all items from XPANDA
python xpanda_fetch_all_items.py
```

---

## Deployment (Railway)

1. Connect GitHub repo to Railway
2. Set environment variables in Railway dashboard
3. Railway auto-sets `RAILWAY_PUBLIC_DOMAIN` and `PORT`
4. Webhook auto-configures on startup via `lifespan` handler in `app.py`

---

## External APIs

### XPANDA API (p2p.xpanda.pro/api/v1)

Endpoints used:
- `GET /items/prices/` — List all items with prices
- `GET /balance/` — Account balance
- `POST /purchases/` — Create purchase with Steam trade
- `POST /deals/` — Create deal (for gifts)

Authentication: `Authorization: {XPANDA_API_KEY}` header

### Telegram Bot API

- Webhook mode (not polling)
- Payments: Telegram Stars (XTR currency)
- WebApp integration for inline keyboard buttons

---

## Common Issues

1. **Webhook not working**: Check `RAILWAY_PUBLIC_DOMAIN` is set
2. **Database errors**: Ensure `DATABASE_URL` uses `postgresql+asyncpg://` scheme
3. **Items not loading**: Check XPANDA API key and balance
4. **Payment failures**: Verify trade link format and Steam inventory privacy
