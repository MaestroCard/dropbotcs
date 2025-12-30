import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from aiogram.methods import CreateInvoiceLink
from database import async_session, get_user, User, update_steam

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)  # Один экземпляр бота для генерации инвойсов

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web_app", StaticFiles(directory="web_app", html=True), name="web_app")

@app.get("/api/profile/{telegram_id}")
async def get_profile(telegram_id: int):
    user = await get_user(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    items = json.loads(user.items_received) if user.items_received else []
    return {
        "referrals": user.referrals,
        "items": items,
        "steam_profile": user.steam_profile,
        "trade_link": user.trade_link
    }

@app.post("/api/bind/{telegram_id}")
async def bind_steam(telegram_id: int, data: dict = Body(...)):
    await update_steam(telegram_id, data.get("profile"), data.get("trade_link"))
    return {"status": "success"}

@app.get("/api/items")
async def get_items():
    return [
        {
            "id": 1,
            "name": "AK-47 | Redline (Field-Tested)",
            "price_stars": 5,  # Для теста минимальная цена
            "image": "https://community.cloudflare.steamstatic.com/economy/image/-9a81dlWLwJ2UUGcVs_nsVtzdOEdtWwKGZZLQHTxDZ7I56KU0Zwwo4NUX4oFJZEHLbXH5ApeO4YmlhxYQknCRvCo04DEVlxkKgpou-6kejhz2v_Nfz5H_uO3mb-Gw_alIITTl3hZ6pZ0iLyS89T3jQzk_0U_MWGhJtKQegD6wbjq1tO-74TPyXFn7HEn5SrbzQv330-/360fx360f"
        },
        {
            "id": 2,
            "name": "AWP | Dragon Lore (Factory New)",
            "price_stars": 10,
            "image": "https://community.cloudflare.steamstatic.com/economy/image/-9a81dlWLwJ2UUGcVs_nsVtzdOEdtWwKGZZLQHTxDZ7I56KU0Zwwo4NUX4oFJZEHLbXH5ApeO4YmlhxYQknCRvCo04DEVlxkKgpot621FABz7PLfYQJH9c63mYW0mOX1IK7dhHti1_dffJ0Kidnxi1Hh80JqZjvyLIfEegVvZFHQrJOj6YmF2pG_78nXnSFrpGB37CPerUepwUYbZ1z2qA8/360fx360f"
        }
    ]

# Новый эндпоинт для генерации ссылки на оплату Stars
@app.post("/api/create_invoice")
async def create_invoice(data: dict):
    item_id = data.get('item_id')
    user_id = data.get('user_id')
    price_stars = data.get('price_stars')

    if not all([item_id, user_id, price_stars]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Название предмета (можно расширить словарём)
    item_name = "AK-47 | Redline" if item_id == 1 else "AWP | Dragon Lore"

    try:
        invoice_link = await bot(CreateInvoiceLink(
            title=f"Покупка: {item_name}",
            description="Предмет из CS2 Marketplace",
            payload=json.dumps({"item_id": item_id, "user_id": user_id}),
            provider_token="",  # Пусто для Stars
            currency="XTR",
            prices=[{"label": item_name, "amount": price_stars}]
        ))
        return {"invoice_link": invoice_link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))