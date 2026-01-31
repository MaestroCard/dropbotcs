from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot
from aiogram.methods import CreateInvoiceLink
from aiogram.types import Update
from dotenv import load_dotenv
import os
import json
import aiohttp
import time  # ← добавлено для кулдауна
from database import async_session, get_user, update_steam
from cache import cache
from bot import dp  # dp из bot.py
from database import add_user

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "your-very-long-secret-token-here-change-me")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")
if not XPANDA_API_KEY:
    raise RuntimeError("XPANDA_API_KEY не найден в .env")

bot = Bot(token=BOT_TOKEN)

XPANDA_BASE_URL = "https://p2p.xpanda.pro/api/v1"

xpanda_headers = {
    "Authorization": XPANDA_API_KEY,
    "Content-Type": "application/json"
}

# Глобальный кулдаун по item_id (60 секунд между созданием инвойсов для одного предмета)
item_cooldowns = {}  # {item_id: timestamp последнего создания инвойса}


async def get_fresh_price(product_id: str):
    url = f"{XPANDA_BASE_URL}/items/prices/"
    params = {"names[]": product_id}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=xpanda_headers, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("items", [])
                    for item in items:
                        if item.get("n") == product_id:
                            return item.get("p", 0), item.get("q", 0)
                    return None, None
                else:
                    print(f"[FRESH PRICE] Ошибка {resp.status}")
                    return None, None
    except Exception as e:
        print(f"[FRESH PRICE ERROR] {type(e).__name__}: {str(e)}")
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('PUBLIC_DOMAIN')
    if not domain:
        raise RuntimeError("Не найден публичный домен (RAILWAY_PUBLIC_DOMAIN)")

    webhook_url = f"https://{domain}/webhook"

    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        print(f"Webhook успешно установлен: {webhook_url}")
    except Exception as e:
        print(f"Ошибка установки webhook: {str(e)}")

    yield

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook удалён")
    except Exception as e:
        print(f"Ошибка удаления webhook: {str(e)}")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web_app", StaticFiles(directory="web_app", html=True), name="web_app")


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    update: Update,
    x_telegram_bot_api_secret_token: str = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token")
):
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/api/profile/{telegram_id}")
async def get_profile(telegram_id: int):
    user = await get_user(telegram_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден. Напишите боту /start, чтобы зарегистрироваться."
        )
    
    items = json.loads(user.items_received) if user.items_received else []
    return {
        "referrals": user.referrals,
        "items": items,
        "steam_profile": user.steam_profile,
        "trade_link": user.trade_link,
        "has_gift": user.has_gift
    }


@app.post("/api/bind/{telegram_id}")
async def bind_steam(telegram_id: int, data: dict = Body(...)):
    profile = data.get("profile")
    trade_link = data.get("trade_link")

    if not profile or not trade_link:
        raise HTTPException(status_code=400, detail="Не указаны profile или trade_link")

    await update_steam(telegram_id, profile, trade_link)
    return {"status": "ok"}


@app.get("/api/items")
async def get_items(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=5, le=100),
    search: str = Query(""),
    balance_check: bool = Query(False)
):
    if not cache.all_items:
        return {"items": [], "total": 0, "page": page, "pages": 1, "message": "Кэш ещё не загружен"}

    filtered = cache.all_items
    if search.strip():
        search_lower = search.lower().strip()
        filtered = [item for item in cache.all_items if search_lower in item["name"].lower()]

    if balance_check:
        available = cache.balance.get("available", 0)
        if available > 0:
            filtered = [item for item in filtered if item.get("price_rub", 0) <= available]
        else:
            filtered = [item for item in filtered if item.get("price_rub", 0) == 0]

    start = (page - 1) * limit
    paginated = filtered[start:start + limit]

    for item in paginated:
        item["product_id"] = item.get("product_id", item["name"])

    total = len(filtered)
    pages = (total + limit - 1) // limit if limit > 0 else 1

    return {
        "items": paginated,
        "total": total,
        "page": page,
        "pages": pages,
        "cache_timestamp": cache.cache_timestamp.isoformat() if cache.cache_timestamp else None,
        "available_balance": cache.balance.get("available", 0)
    }


@app.get("/api/balance")
async def get_balance():
    return {
        "available": cache.balance["available"],
        "total": cache.balance["total"],
        "locked": cache.balance["locked"]
    }


@app.get("/api/item_price")
async def get_item_price(product_id: str = Query(...)):
    fresh_rub, fresh_qty = await get_fresh_price(product_id)
    if fresh_rub is None:
        raise HTTPException(status_code=503, detail="Не удалось получить актуальную цену")
    return {"price_rub": fresh_rub, "quantity": fresh_qty}


@app.post("/api/create_invoice")
async def create_invoice(data: dict):
    print("[DEBUG INVOICE] Полученные данные:", data)

    item_id = data.get('item_id')
    product_id = data.get('product_id')
    user_id = data.get('user_id')
    price_stars = data.get('price_stars')

    missing = []
    if not item_id: missing.append('item_id')
    if not product_id: missing.append('product_id')
    if not user_id: missing.append('user_id')
    if not price_stars: missing.append('price_stars')

    if missing:
        print("[DEBUG INVOICE] Отсутствуют поля:", missing)
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.trade_link:
        raise HTTPException(status_code=400, detail="Trade link не привязан. Привяжите trade link в профиле перед покупкой.")

    # Глобальный кулдаун по item_id (60 секунд)
    now = time.time()
    last_time = item_cooldowns.get(item_id, 0)
    if now - last_time < 60:
        raise HTTPException(status_code=429, detail="Предмет временно недоступен. Повторите попытку позже.")

    item_name = f"Предмет ID {item_id}"

    try:
        invoice_link = await bot(CreateInvoiceLink(
            title=f"Покупка: {item_name}",
            description="Скин CS2 из маркетплейса",
            payload=json.dumps({"item_id": item_id, "product_id": product_id, "user_id": user_id}),
            provider_token="",
            currency="XTR",
            prices=[{"label": item_name, "amount": price_stars}]
        ))

        # Обновляем кулдаун после успешного создания инвойса
        item_cooldowns[item_id] = now

        return {"invoice_link": invoice_link}
    except Exception as e:
        print("[ERROR INVOICE] Telegram API error:", str(e))
        raise HTTPException(status_code=500, detail=f"Telegram invoice error: {str(e)}")


@app.post("/api/create_deal")
async def create_deal(data: dict):
    user_id = data.get('user_id')
    item_id = data.get('item_id')

    if not user_id or not item_id:
        raise HTTPException(status_code=400, detail="Missing user_id or item_id")

    user = await get_user(user_id)
    if not user or not user.trade_link:
        raise HTTPException(status_code=400, detail="Trade link not set in profile")

    payload = {
        "item_id": item_id,
        "trade_url": user.trade_link
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{XPANDA_BASE_URL}/deals",
                json=payload,
                headers=xpanda_headers,
                timeout=20
            ) as resp:
                if resp.status in [200, 201]:
                    result = await resp.json()
                    deal_id = result.get('id') or result.get('deal_id')
                    return {"status": "success", "deal_id": deal_id}
                else:
                    error_text = await resp.text()
                    raise HTTPException(status_code=502, detail=f"Xpanda error {resp.status}: {error_text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Deal creation failed: {str(e)}")