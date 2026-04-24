import asyncio
from contextlib import asynccontextmanager
import datetime
import random
import hashlib
import hmac
import uuid
from fastapi import FastAPI, HTTPException, Body, Query, Header, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from aiogram import Bot
from aiogram.methods import CreateInvoiceLink
from aiogram.types import Update
from dotenv import load_dotenv
import os
import json
import aiohttp
import time  # ← добавлено для кулдауна
from database import (
    async_session, get_user, update_steam, add_user,
    freeze_user, approve_user, dismiss_review,
    get_users_for_review, get_all_referrers_paginated,
    get_referral_tree, get_referrals_per_day,
    admin_add_referral, admin_increment_referrals,
    freeze_subtree,
)
from cache import cache
from bot import dp  # dp из bot.py
from config import OWNER_ID, ADMIN_TOKEN
from bot_settings import bot_settings
from cardlink_payment import create_payment, check_payment_status

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
XPANDA_SECRET = os.getenv('XPANDA_SECRET', '')
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

# Хранилище данных о платежах Cardlink (order_id -> данные)
cardlink_payments = {}  # {order_id: {"user_id": ..., "item_id": ..., "product_id": ..., "timestamp": ...}}


async def send_gift_notifications(user_id: int, skin_name: str, skin_image: str, price_rub: int, deal_id: str, trade_link: str):
    """Фоновая задача: отправляет уведомления с задержкой (чтобы не блокировать WebApp)"""
    await asyncio.sleep(8)  # Ждём окончания анимации рулетки
    
    try:
        # Уведомление пользователю
        await bot.send_message(
            user_id,
            f"🎉 <b>Подарок отправлен в трейд!</b>\n\n"
            f"Скин: <b>{skin_name}</b>\n"
            f"ID сделки: <code>{deal_id}</code>\n\n"
            f"Проверьте Steam через 1–5 минут.",
            parse_mode="HTML"
        )

        # Лог владельцу
        await bot.send_message(
            OWNER_ID,
            f"✅ ПОДАРОК ВЫДАН\n"
            f"User: {user_id}\n"
            f"Скин: {skin_name}\n"
            f"Цена: ${price_rub / 1000:.2f}\n"
            f"Deal ID: {deal_id}\n"
            f"Trade link: {trade_link}"
        )
    except Exception as e:
        print(f"[NOTIFY ERROR] Ошибка отправки уведомлений: {e}")


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
        await bot.send_message(OWNER_ID,f"🚀 Сервер запущен\nWebhook: {webhook_url}")  # ← новое
    except Exception as e:
        print(f"Ошибка установки webhook: {str(e)}")
        await bot.send_message(OWNER_ID,f"❌ Ошибка установки webhook:\n{str(e)}")  # ← новое

    yield

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook удалён")
        await bot.send_message(OWNER_ID,"🛑 Сервер остановлен, webhook удалён")  # ← новое
    except Exception as e:
        print(f"Ошибка удаления webhook: {str(e)}")
        await bot.send_message(OWNER_ID,f"❌ Ошибка удаления webhook:\n{str(e)}")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web_app", StaticFiles(directory="web_app", html=True), name="web_app")
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")

# ─── Admin auth dependency ─────────────────────────────────────────────────────
_admin_bearer = HTTPBearer(auto_error=False)

async def require_admin(
    creds: HTTPAuthorizationCredentials = Depends(_admin_bearer),
):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN не задан на сервере")
    if not creds or creds.credentials != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ─── Admin API endpoints ───────────────────────────────────────────────────────

def _user_to_dict(user) -> dict:
    return {
        "telegram_id":      user.telegram_id,
        "referrals":        user.referrals,
        "frozen_referrals": user.frozen_referrals or 0,
        "is_frozen":        bool(user.is_frozen),
        "needs_review":     bool(user.needs_review),
        "joined_at":        user.joined_at.isoformat() if user.joined_at else None,
        "has_gift":         user.has_gift,
        "steam_profile":    user.steam_profile,
        "trade_link":       user.trade_link,
        "referred_by":      user.referred_by,
    }


@app.get("/api/admin/users", dependencies=[Depends(require_admin)])
async def admin_get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("referrals"),
    sort_dir: str = Query("desc"),
):
    allowed_sort = {"referrals", "joined_at", "telegram_id"}
    if sort_by not in allowed_sort:
        sort_by = "referrals"
    data = await get_all_referrers_paginated(page, limit, sort_by, sort_dir)
    return {
        "users": [_user_to_dict(u) for u in data["users"]],
        "total": data["total"],
        "page":  data["page"],
        "pages": data["pages"],
    }


@app.get("/api/admin/review_queue", dependencies=[Depends(require_admin)])
async def admin_review_queue():
    users = await get_users_for_review()
    return {
        "users": [_user_to_dict(u) for u in users],
        "count": len(users),
    }


@app.get("/api/admin/user/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_get_user(telegram_id: int):
    user = await get_user(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _user_to_dict(user)


@app.post("/api/admin/freeze/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_freeze(telegram_id: int, data: dict = Body(...)):
    freeze = bool(data.get("freeze", True))
    ok = await freeze_user(telegram_id, freeze)
    if not ok:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Уведомить пользователя
    try:
        if freeze:
            await bot.send_message(
                telegram_id,
                "⚠️ Ваш реферальный аккаунт временно заморожен.\n"
                "Новые рефералы не будут засчитываться до окончания проверки.\n"
                "Ранее приглашённые вами пользователи сохранены и будут восстановлены автоматически.",
            )
        else:
            await bot.send_message(
                telegram_id,
                "✅ Ваш реферальный аккаунт разморожен!\n"
                "Все рефералы восстановлены, новые снова засчитываются.",
            )
    except Exception as e:
        print(f"[FREEZE NOTIFY] Ошибка отправки уведомления {telegram_id}: {e}")

    return {"ok": True, "telegram_id": telegram_id, "is_frozen": freeze}


@app.post("/api/admin/approve/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_approve(telegram_id: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    result = await approve_user(telegram_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Уведомление о разморозке
    try:
        await bot.send_message(
            telegram_id,
            "✅ Ваш реферальный аккаунт разморожен!\n"
            "Все рефералы восстановлены, новые снова засчитываются.",
        )
    except Exception as e:
        print(f"[APPROVE UNFREEZE NOTIFY] {e}")

    # Отправляем уведомление о подарке за каждого восстановленного реферала
    restored = result["restored"]
    gifts_sent = 0
    if restored > 0:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")
        ]])
        for i in range(restored):
            try:
                await bot.send_message(
                    telegram_id,
                    f"🎉 Один из ваших рефералов был засчитан после проверки аккаунта!\n"
                    f"У вас теперь <b>{result['referrals_before'] + i + 1}</b> рефералов.\n"
                    f"Нажмите кнопку ниже, чтобы получить подарок — случайный скин CS2.",
                    reply_markup=markup,
                    parse_mode="HTML",
                )
                gifts_sent += 1
                await asyncio.sleep(0.05)  # защита от flood control Telegram
            except Exception as e:
                print(f"[APPROVE GIFT NOTIFY {i+1}/{restored}] Ошибка: {e}")

    return {
        "ok":               True,
        "telegram_id":      telegram_id,
        "referrals_before": result["referrals_before"],
        "referrals_after":  result["referrals_after"],
        "restored":         restored,
        "gifts_sent":       gifts_sent,
    }


@app.post("/api/admin/freeze_subtree/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_freeze_subtree(telegram_id: int, data: dict = Body(...)):
    freeze = bool(data.get("freeze", True))
    result = await freeze_subtree(telegram_id, freeze)

    # Уведомляем пользователей (не более 30/сек, защита от flood control)
    notified = 0
    for i, uid in enumerate(result["ids"]):
        try:
            if freeze:
                await bot.send_message(
                    uid,
                    "⚠️ Ваш реферальный аккаунт временно заморожен.\n"
                    "Новые рефералы не будут засчитываться до окончания проверки.",
                )
            else:
                await bot.send_message(
                    uid,
                    "✅ Ваш реферальный аккаунт разморожен!\n"
                    "Новые рефералы снова засчитываются.",
                )
            notified += 1
        except Exception as e:
            print(f"[SUBTREE NOTIFY] {uid}: {e}")
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)

    return {
        "ok":       True,
        "frozen":   freeze,
        "affected": result["affected"],
        "notified": notified,
    }


@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
async def admin_get_settings():
    return {"gifts_enabled": bot_settings.gifts_enabled}


@app.post("/api/admin/settings/gifts_toggle", dependencies=[Depends(require_admin)])
async def admin_toggle_gifts():
    bot_settings.gifts_enabled = not bot_settings.gifts_enabled
    state = "включена" if bot_settings.gifts_enabled else "отключена"
    print(f"[ADMIN] Выдача подарков {state}")
    try:
        await bot.send_message(OWNER_ID, f"🎁 Выдача подарков {state} через админ-панель.")
    except Exception:
        pass
    return {"gifts_enabled": bot_settings.gifts_enabled}


@app.post("/api/admin/dismiss/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_dismiss(telegram_id: int):
    ok = await dismiss_review(telegram_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"ok": True, "telegram_id": telegram_id}


@app.get("/api/admin/tree/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_tree(telegram_id: int, depth: int = Query(3, ge=1, le=4)):
    tree = await get_referral_tree(telegram_id, max_depth=depth)
    return tree


@app.get("/api/admin/stats/referrals_per_day", dependencies=[Depends(require_admin)])
async def admin_referrals_per_day(days: int = Query(30, ge=1, le=365)):
    data = await get_referrals_per_day(days)
    return {"data": data, "days": days}


@app.post("/api/admin/add_referral", dependencies=[Depends(require_admin)])
async def admin_add_referral_endpoint(data: dict = Body(...)):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    referrer_id = data.get("referrer_id")
    invited_id  = data.get("invited_id")

    if not referrer_id or not invited_id:
        raise HTTPException(status_code=400, detail="Нужны referrer_id и invited_id")

    result = await admin_add_referral(int(referrer_id), int(invited_id))

    if not result["ok"]:
        reason_ru = {
            "self_referral":       "Самореферал невозможен",
            "inviter_not_found":   "Пригласивший не найден",
            "invited_not_found":   "Приглашённый не найден",
            "already_has_referrer": "У пользователя уже есть реферер",
        }.get(result["reason"], result["reason"])
        raise HTTPException(status_code=400, detail=reason_ru)

    # Отправить уведомление о подарке инвайтеру
    try:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")
        ]])
        await bot.send_message(
            referrer_id,
            f"🎉 Администратор вручную засчитал вам реферала!\n"
            f"У вас теперь <b>{result['referrals_count']}</b> рефералов.\n"
            f"Нажмите кнопку ниже, чтобы получить подарок — случайный скин CS2.",
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"[ADMIN ADD REFERRAL NOTIFY] Ошибка: {e}")

    return {
        "ok":             True,
        "referrer_id":    referrer_id,
        "invited_id":     invited_id,
        "referrals_count": result["referrals_count"],
    }


@app.post("/api/admin/increment_referrals/{telegram_id}", dependencies=[Depends(require_admin)])
async def admin_increment_endpoint(telegram_id: int, data: dict = Body(...)):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    count = int(data.get("count", 1))
    result = await admin_increment_referrals(telegram_id, count)

    if not result["ok"]:
        reason_ru = {
            "inviter_not_found": "Пользователь не найден",
            "invalid_count":     "Некорректное количество (1–10000)",
        }.get(result["reason"], result["reason"])
        raise HTTPException(status_code=400, detail=reason_ru)

    # Отправить уведомление о подарке за каждый добавленный реферал
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")
    ]])
    gifts_sent = 0
    start_count = result["referrals_count"] - count
    for i in range(count):
        try:
            await bot.send_message(
                telegram_id,
                f"🎉 Администратор вручную засчитал вам реферала!\n"
                f"У вас теперь <b>{start_count + i + 1}</b> рефералов.\n"
                f"Нажмите кнопку ниже, чтобы получить подарок — случайный скин CS2.",
                reply_markup=markup,
                parse_mode="HTML",
            )
            gifts_sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"[INCREMENT NOTIFY {i+1}/{count}] {e}")

    return {
        "ok":             True,
        "telegram_id":    telegram_id,
        "added":          count,
        "referrals_count": result["referrals_count"],
        "gifts_sent":     gifts_sent,
    }


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

    # Формируем ответ с ценами в рублях для отображения
    result_items = []
    for item in paginated:
        item_data = dict(item)  # Копируем, чтобы не менять оригинал
        item_data["product_id"] = item.get("product_id", item["name"])
        # Добавляем цену в рублях для отображения
        item_data["price_rub_display"] = item.get("price_rub_display", item.get("price_stars", 0))
        result_items.append(item_data)

    total = len(filtered)
    pages = (total + limit - 1) // limit if limit > 0 else 1

    return {
        "items": result_items,
        "total": total,
        "page": page,
        "pages": pages,
        "cache_timestamp": cache.cache_timestamp.isoformat() if cache.cache_timestamp else None,
        "available_balance": cache.balance.get("available", 0),
        "usd_rate": cache.usd_rate,
        "markup": cache.markup,
        "cardlink_commission": cache.cardlink_commission
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
        await bot.send_message(OWNER_ID,f"❌ Ошибка создания инвойса\nUser: {user_id}\nItem ID: {item_id}\nОшибка: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Telegram invoice error: {str(e)}")


@app.post("/api/create_rub_invoice")
async def create_rub_invoice(data: dict):
    """Создаёт ссылку на оплату рублями через Cardlink"""
    item_id = data.get('item_id')
    product_id = data.get('product_id')
    user_id = data.get('user_id')
    price_rub_display = data.get('price_rub_display')  # Цена с комиссией (то, что видит пользователь)
    
    if not all([item_id, product_id, user_id]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    if not price_rub_display or int(price_rub_display) <= 0:
        raise HTTPException(status_code=400, detail="Missing price")
    
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.trade_link:
        raise HTTPException(status_code=400, detail="Trade link не привязан")
    
    # Кулдаун
    now = time.time()
    last_time = item_cooldowns.get(item_id, 0)
    if now - last_time < 60:
        raise HTTPException(status_code=429, detail="Предмет временно недоступен. Повторите попытку позже.")
    
    # Создаём платёж через Cardlink
    order_id = f"cs2_{user_id}_{item_id}_{int(now)}"
    # Отправляем ровно ту сумму, что видит пользователь (с комиссией)
    # Комиссию платим мы (payer_pays_commission=0)
    amount_rub = str(int(price_rub_display))
    
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    base_url = f"https://{domain}/payment"
    
    result = await create_payment(
        amount=amount_rub,
        description=f"Покупка {product_id}",
        order_id=order_id,
        base_url=base_url,
        telegram_id=str(user_id),
        trade_link=user.trade_link or "",
        item_name=product_id
    )
    
    if not result["success"]:
        print(f"[CARDLINK ERROR] {result.get('error')}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания платежа: {result.get('error')}")
    
    # Сохраняем информацию о платеже для последующей обработки Success URL
    cardlink_payments[order_id] = {
        "user_id": user_id,
        "item_id": item_id,
        "product_id": product_id,
        "price_rub": int(amount_rub),
        "timestamp": now
    }
    item_cooldowns[item_id] = now
    
    return {
        "payment_url": result["payment_url"],
        "payment_page_url": result.get("payment_page_url"),  # /transfer/ для СБП
        "payment_id": result["payment_id"],
        "order_id": order_id
    }


@app.get("/api/check_payment/{payment_id}")
async def check_payment(payment_id: str):
    """Проверяет статус платежа Cardlink"""
    result = await check_payment_status(payment_id)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Ошибка проверки"))
    
    return {
        "status": result["status"],  # paid, pending, cancelled
        "amount": result.get("amount"),
        "order_id": result.get("order_id")
    }


@app.get("/api/gift_items")
async def get_gift_items():
    """Возвращает топ-20 дешёвых предметов для подарков"""
    if not cache.all_items:
        return {"items": []}
    
    available = [
        item for item in cache.all_items
        if item.get("quantity", 0) > 0 and item.get("price_rub", 0) >= 15
    ]
    
    cheapest = sorted(available, key=lambda x: x.get("price_rub", float("inf")))[:20]
    
    # Форматируем для анимации
    items = [
        {
            "id": item["id"],
            "name": item["name"],
            "image": item["image"],
            "price_rub": item["price_rub"]
        }
        for item in cheapest
    ]
    
    return {"items": items}


@app.post("/api/claim_gift/{user_id}")
async def claim_gift(user_id: int):
    async with async_session() as session:
        async with session.begin():
            user = await get_user(user_id, session)
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            if not bot_settings.gifts_enabled:
                raise HTTPException(status_code=400, detail="Выдача подарков временно приостановлена. Попробуйте позже.")

            if user.is_frozen:
                raise HTTPException(status_code=400, detail="Ваш аккаунт заморожен. Получение подарков недоступно до окончания проверки.")

            if not user.has_gift:
                raise HTTPException(status_code=400, detail="У вас нет доступных подарков. Пригласите друзей по реферальной ссылке, чтобы получить скин!")

            if not user.trade_link:
                user.has_gift = False
                session.add(user)
                raise HTTPException(status_code=400, detail="Trade link не привязан")

            # Топ-20 самых дешёвых для анимации и выдачи
            available = [
                item for item in cache.all_items
                if item.get("quantity", 0) > 0 and item.get("price_rub", 0) >= 15
            ]
            if not available:
                user.has_gift = False
                session.add(user)
                await bot.send_message(
                    OWNER_ID,
                    f"❌ Нет доступных скинов для подарка\nUser: {user_id}"
                )
                raise HTTPException(status_code=503, detail="Нет доступных подарков")

            cheapest = sorted(available, key=lambda x: x.get("price_rub", float("inf")))[:20]
            selected = random.choice(cheapest)

            skin_name = selected["name"]
            skin_image = selected["image"]
            price_rub = selected["price_rub"]
            item_id = selected["id"]

            # Парсим trade_link для partner и token
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(user.trade_link)
            params_trade = parse_qs(parsed.query)
            partner = params_trade.get('partner', [None])[0]
            token = params_trade.get('token', [None])[0]
            
            if not partner or not token:
                user.has_gift = False
                session.add(user)
                raise HTTPException(status_code=400, detail="Неверный формат trade-ссылки")
            
            # Формируем параметры для XPANDA /purchases/
            params = {
                "product": selected.get("product_id") or selected["name"],
                "partner": partner,
                "token": token,
                "max_price": int(price_rub * 1.2),
                "custom_id": f"gift_{user_id}_{uuid.uuid4().hex[:8]}",
            }
            
            # Создаём подпись HMAC
            params_list = [f"{k}:{v}" for k, v in sorted(params.items()) if v is not None]
            params_string = ';'.join(params_list)
            sign = hmac.new(
                XPANDA_SECRET.encode(),
                params_string.encode(),
                hashlib.sha256
            ).hexdigest()
            params["sign"] = sign

            # Создаём сделку в XPANDA
            async with aiohttp.ClientSession() as aio_session:
                try:
                    async with aio_session.post(
                        f"{XPANDA_BASE_URL}/purchases/",
                        json=params,
                        headers=xpanda_headers,
                        timeout=25
                    ) as resp:
                        if resp.status not in (200, 201):
                            error_text = await resp.text()
                            user.has_gift = False
                            session.add(user)
                            await bot.send_message(
                                OWNER_ID,
                                f"❌ Ошибка XPANDA при выдаче подарка\n"
                                f"User: {user_id}\n"
                                f"Скин: {skin_name}\n"
                                f"Статус: {resp.status}\n"
                                f"Ответ: {error_text[:400]}"
                            )
                            raise HTTPException(status_code=502, detail=f"Xpanda error: {resp.status}")

                        result = await resp.json()
                        deal_id = result.get('id') or result.get('deal_id', 'N/A')

                except Exception as e:
                    user.has_gift = False
                    session.add(user)
                    await bot.send_message(
                        OWNER_ID,
                        f"❌ Исключение при создании сделки подарка\n"
                        f"User: {user_id}\n"
                        f"Ошибка: {type(e).__name__}: {str(e)}"
                    )
                    raise HTTPException(status_code=500, detail=str(e))

            # Сбрасываем флаг сразу (до отправки уведомлений)
            user.has_gift = False
            session.add(user)

            # Возвращаем данные для WebApp СРАЗУ (не ждём уведомлений)
            # Уведомления отправим фоново с задержкой
            asyncio.create_task(
                send_gift_notifications(user_id, skin_name, skin_image, price_rub, deal_id, user.trade_link)
            )

            return {
                "success": True,
                "name": skin_name,
                "image": skin_image,
                "deal_id": deal_id
            }


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
                timeout=25
            ) as resp:
                if resp.status not in (200, 201):
                    error_text = await resp.text()
                    raise HTTPException(status_code=502, detail=f"Xpanda error: {resp.status} - {error_text[:200]}")
                
                result = await resp.json()
                return {"status": "ok", "deal_id": result.get('id') or result.get('deal_id')}
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

async def process_cardlink_payment(user_id: int, item_id: int, product_id: str, price_rub: int = None, inv_id: str = None):
    """Обработка успешной оплаты Cardlink - создание сделки в XPANDA"""
    from urllib.parse import urlparse, parse_qs
    
    user = await get_user(user_id)
    if not user or not user.trade_link:
        print(f"[CARDLINK] Ошибка: Trade link не привязан для user={user_id}")
        return False, "Trade link не привязан"
    
    # Парсим trade_link
    try:
        parsed = urlparse(user.trade_link)
        params = parse_qs(parsed.query)
        partner = params.get('partner', [None])[0]
        token = params.get('token', [None])[0]
        
        if not partner or not token:
            return False, "Неверный формат trade-ссылки"
    except Exception as e:
        return False, f"Ошибка парсинга trade-ссылки: {e}"
    
    # Находим актуальную цену предмета
    actual_price_rub = None
    for item in cache.all_items:
        if item.get("product_id") == product_id or item.get("name") == product_id:
            actual_price_rub = item.get("price_rub")
            break
    
    if actual_price_rub is None:
        return False, "Не удалось найти актуальную цену предмета"
    
    max_price = int(actual_price_rub * 1.2)
    
    # Формируем параметры для XPANDA
    # Используем inv_id (order_id из Cardlink) как custom_id для удобства поиска
    custom_id = inv_id if inv_id else f"cardlink_{user_id}_{uuid.uuid4().hex[:8]}"
    params = {
        "product": product_id,
        "partner": partner,
        "token": token,
        "max_price": max_price,
        "custom_id": custom_id,
    }
    
    # Создаём подпись HMAC
    params_list = [f"{k}:{v}" for k, v in sorted(params.items()) if v is not None]
    params_string = ';'.join(params_list)
    sign = hmac.new(
        XPANDA_SECRET.encode(),
        params_string.encode(),
        hashlib.sha256
    ).hexdigest()
    params["sign"] = sign
    
    # Цена для логов (в рублях)
    price_rub_display = price_rub if price_rub else actual_price_rub
    
    # Отправляем запрос в XPANDA
    url = f"{XPANDA_BASE_URL}/purchases/"
    print(f"[CARDLINK] Создание сделки в XPANDA: user={user_id}, item={product_id}, price={price_rub_display}₽")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=params,
                headers=xpanda_headers,
                timeout=30
            ) as resp:
                text = await resp.text()
                print(f"[CARDLINK] XPANDA ответ: {resp.status}, {text[:500]}")
                
                if resp.status in [200, 201]:
                    result = json.loads(text)
                    deal_id = result.get('id', 'неизвестно')
                    
                    # Отправляем уведомление пользователю
                    await bot.send_message(
                        user_id,
                        f"💳 Оплата прошла успешно! Предмет отправлен в трейд.\n"
                        f"ID сделки: {deal_id}\n"
                        f"Проверьте Steam: {user.trade_link}"
                    )
                    
                    # Уведомление владельцу
                    await bot.send_message(
                        OWNER_ID,
                        f"💰 ПРОДАЖА ЧЕРЕЗ СБП (Cardlink)\n"
                        f"User ID: {user_id}\n"
                        f"Предмет: {product_id}\n"
                        f"Сумма: {price_rub_display}₽\n"
                        f"ID сделки: {deal_id}\n"
                        f"Trade link: {user.trade_link}"
                    )
                    return True, deal_id
                else:
                    error_msg = f"Ошибка XPANDA: {resp.status} - {text[:300]}"
                    print(f"[CARDLINK] {error_msg}")
                    await bot.send_message(OWNER_ID, f"❌ {error_msg}\nUser: {user_id}")
                    return False, error_msg
                    
    except Exception as e:
        error_msg = f"Исключение при создании сделки: {type(e).__name__}: {str(e)}"
        print(f"[CARDLINK] {error_msg}")
        await bot.send_message(OWNER_ID, f"❌ {error_msg}\nUser: {user_id}")
        return False, error_msg


async def log_cardlink_request(request: Request, endpoint_name: str, skip_telegram: bool = False):
    """Подробное логирование запроса от Cardlink для отладки"""
    # Получаем form_data и body ДО логирования (тело можно прочитать только раз)
    form_data_dict = {}
    raw_body = ""
    
    try:
        # Пытаемся получить body как текст СНАЧАЛА
        body = await request.body()
        raw_body = body.decode('utf-8', errors='ignore')[:2000]
    except Exception as e:
        raw_body = f"Could not read body: {e}"
    
    # Парсим form-data из raw_body вручную, если стандартный парсер не работает
    if raw_body and "=" in raw_body:
        try:
            from urllib.parse import parse_qs
            parsed = parse_qs(raw_body)
            form_data_dict = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        except Exception as e:
            form_data_dict = {"parse_error": str(e), "raw": raw_body[:500]}
    
    log_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "endpoint": endpoint_name,
        "url": str(request.url),
        "method": request.method,
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "form_data": form_data_dict,
        "raw_body": raw_body,
    }
    
    log_text = f"""
=== CARDLINK DEBUG LOG ===
Timestamp: {log_data['timestamp']}
Endpoint: {log_data['endpoint']}
URL: {log_data['url']}
Method: {log_data['method']}

PARSED FORM DATA:
{json.dumps(form_data_dict, indent=2, ensure_ascii=False)}

RAW BODY:
{raw_body}
=========================
"""
    print(log_text)
    
    # Отправляем в Telegram для видимости (кроме SUCCESS и RESULT)
    if not skip_telegram:
        try:
            await bot.send_message(
                OWNER_ID,
                f"📋 Cardlink ({endpoint_name}):\n"
                f"URL: {log_data['url']}\n"
                f"Form: {json.dumps(form_data_dict, ensure_ascii=False)[:800]}"
            )
        except Exception as e:
            print(f"[DEBUG] Failed to send Telegram log: {e}")
    
    return log_data


def payment_result_html(status: str, message: str = "", deal_id: str = ""):
    """Генерирует простую HTML страницу результата платежа"""
    
    # Все статусы показывают одно и то же - статус отправлен в чат
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Статус оплаты</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                margin: 0;
            }
            .card {
                background: #ffffff;
                border-radius: 20px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }
            h1 {
                color: #1e293b;
                font-size: 22px;
                margin-bottom: 20px;
            }
            p {
                color: #64748b;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 15px;
            }
            .btn {
                display: inline-block;
                background: #3b82f6;
                color: white;
                text-decoration: none;
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 600;
                margin-top: 20px;
            }
            .btn:hover { background: #2563eb; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>✅ Платёж обработан</h1>
            <p>Статус оплаты отправлен вам в чат с ботом.</p>
            <p>Проверьте Telegram для получения деталей.</p>
            <a href="https://t.me/QuestixMarketBot" class="btn">Перейти в бота</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/payment/success")
async def cardlink_success(request: Request):
    """Обработка успешной оплаты от Cardlink - показывает простую HTML страницу"""
    log = await log_cardlink_request(request, "SUCCESS", skip_telegram=True)
    
    form_data = log.get("form_data", {})
    inv_id = form_data.get("InvId")
    
    print(f"[CARDLINK SUCCESS] Received: InvId={inv_id}")
    
    if inv_id and inv_id in cardlink_payments:
        payment_data = cardlink_payments[inv_id]
        user_id = payment_data["user_id"]
        item_id = payment_data["item_id"]
        product_id = payment_data["product_id"]
        price_rub = payment_data.get("price_rub")
        del cardlink_payments[inv_id]
        
        # Обрабатываем платёж в фоне (не блокируем показ страницы)
        try:
            success, result = await process_cardlink_payment(user_id, item_id, product_id, price_rub, inv_id)
            print(f"[CARDLINK SUCCESS] Processed: success={success}, deal={result}")
        except Exception as e:
            print(f"[CARDLINK SUCCESS] Processing error (non-blocking): {e}")
    
    # Всегда показываем успешную страницу
    return payment_result_html("success")


@app.post("/payment/fail")
async def cardlink_fail(request: Request):
    """Обработка неуспешной оплаты от Cardlink"""
    log = await log_cardlink_request(request, "FAIL")
    
    form_data = log.get("form_data", {})
    inv_id = form_data.get("InvId")
    
    print(f"[CARDLINK FAIL] Received: InvId={inv_id}")
    
    if inv_id and inv_id in cardlink_payments:
        del cardlink_payments[inv_id]
    
    # Показываем ту же страницу (сообщение о статусе в чате)
    return payment_result_html("fail")


@app.post("/payment/result")
async def cardlink_result(request: Request):
    """Обработка результата от Cardlink (основной callback с Status=SUCCESS)"""
    log = await log_cardlink_request(request, "RESULT", skip_telegram=True)
    
    form_data = log.get("form_data", {})
    inv_id = form_data.get("InvId")
    status = form_data.get("Status")
    
    print(f"[CARDLINK RESULT] Received: InvId={inv_id}, Status={status}")
    
    # Cardlink отправляет SUCCESS в result URL!
    if status == "SUCCESS" and inv_id:
        print(f"[CARDLINK RESULT] Processing successful payment: {inv_id}")
        
        # Получаем данные о платеже
        payment_data = cardlink_payments.get(inv_id)
        
        if not payment_data:
            print(f"[CARDLINK RESULT] Payment data not found, trying to parse order_id: {inv_id}")
            try:
                parts = inv_id.split("_")
                if len(parts) >= 4 and parts[0] == "cs2":
                    user_id = int(parts[1])
                    item_id = int(parts[2])
                    product_id = None
                    for item in cache.all_items:
                        if item.get("id") == item_id:
                            product_id = item.get("product_id") or item.get("name")
                            break
                    if not product_id:
                        return {"status": "error", "message": "Item not found"}
                else:
                    return {"status": "error", "message": "Invalid order_id format"}
            except Exception as e:
                print(f"[CARDLINK RESULT] Parse error: {e}")
                return {"status": "error", "message": str(e)}
        else:
            user_id = payment_data["user_id"]
            item_id = payment_data["item_id"]
            product_id = payment_data["product_id"]
            price_rub = payment_data.get("price_rub")
            del cardlink_payments[inv_id]
        
        # Создаём сделку
        try:
            success, result = await process_cardlink_payment(user_id, item_id, product_id, price_rub, inv_id)
            if success:
                print(f"[CARDLINK RESULT] Deal created: {result}")
                return {"status": "ok", "deal_id": result}
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            print(f"[CARDLINK RESULT] Exception: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
    
    return {"status": "ok", "received": True}
