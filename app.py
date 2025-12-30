import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, get_user, User, update_steam  # Добавлен update_steam
from database import engine as db_engine  # Для Depends если нужно

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Для dev; на прод ограничи
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
    # Заглушка; замени на await aiohttp.get('your_api_url')
    return [
        {"id": 1, "name": "AK-47 | Redline", "price_stars": 100, "image": "https://example.com/ak.jpg"},
        {"id": 2, "name": "AWP | Dragon Lore", "price_stars": 5000, "image": "https://example.com/awp.jpg"}
    ]