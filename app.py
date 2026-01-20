import json
import os
from datetime import datetime
from asyncio import create_task, sleep
from dotenv import load_dotenv
import aiohttp
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot
from aiogram.methods import CreateInvoiceLink
from database import async_session, get_user, update_steam

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')

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

# Глобальный кэш всех предметов и время последнего обновления
all_items_cache = []  # Полный список предметов (без пагинации)
cache_timestamp = None
CACHE_UPDATE_INTERVAL = 600  # 10 минут в секундах

# Курс RUB to USD
RUB_PER_USD = 82.0  # Обновляйте по мере необходимости

# Загрузка трёх отдельных JSON-файлов для картинок
skins_data = []
crates_data = []
stickers_data = []

try:
    with open('data/skins.json', 'r', encoding='utf-8') as f:
        skins_data = json.load(f)
    print(f"Загружено {len(skins_data)} скинов")
except FileNotFoundError:
    print("skins.json не найден")

try:
    with open('data/crates.json', 'r', encoding='utf-8') as f:
        crates_data = json.load(f)
    print(f"Загружено {len(crates_data)} кейсов")
except FileNotFoundError:
    print("crates.json не найден")

try:
    with open('data/stickers.json', 'r', encoding='utf-8') as f:
        stickers_data = json.load(f)
    print(f"Загружено {len(stickers_data)} стикеров")
except FileNotFoundError:
    print("stickers.json не найден")

# Улучшенная функция поиска изображения (твоя версия без изменений)
def get_skin_image(name: str) -> str:
    name_lower = name.lower().strip()

    # Очищаем название
    cleaned_name = name_lower
    cleaned_name = cleaned_name.replace('stattrak™ ', '')
    cleaned_name = cleaned_name.split('(')[0].strip()

    # 1. Скины оружия, ножи, перчатки — из skins.json
    for skin in skins_data:
        skin_name = skin.get('name', '').lower()
        market_hash = skin.get('market_hash_name', '').lower()
        if cleaned_name in skin_name or cleaned_name in market_hash:
            img = skin.get('image')
            if img:
                return img

    # 2. Кейсы — из crates.json
    for crate in crates_data:
        crate_name = crate.get('name', '').lower()
        if name_lower == crate_name or cleaned_name in crate_name:
            img = crate.get('image')
            if img:
                return img

    # 3. Стикеры — из stickers.json
    for sticker in stickers_data:
        sticker_name = sticker.get('name', '').lower()
        if cleaned_name in sticker_name or name_lower in sticker_name:
            img = sticker.get('image')
            if img:
                return img

    # Если ничего не нашли — заглушка
    return f"https://via.placeholder.com/80x60?text={name[:20].replace(' ', '+')}"

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
        "trade_link": user.trade_link,
        "has_gift": user.has_gift  # ← Новый флаг
    }


@app.post("/api/bind/{telegram_id}")
async def bind_steam(telegram_id: int, data: dict = Body(...)):
    await update_steam(telegram_id, data.get("profile"), data.get("trade_link"))
    return {"status": "success"}

@app.post("/api/claim_gift/{telegram_id}")
async def claim_gift(telegram_id: int):
    user = await get_user(telegram_id)
    if not user or not user.has_gift:
        raise HTTPException(status_code=400, detail="Подарок недоступен")

    user.has_gift = False
    await async_session.commit()
    return {"status": "success"}

# Фоновая задача обновления полного кэша предметов (раз в 10 минут)
async def update_items_cache():
    global all_items_cache, cache_timestamp
    while True:
        try:
            print(f"[{datetime.now()}] Обновление полного кэша предметов...")
            url = XPANDA_BASE_URL + "/items/prices/"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=xpanda_headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items_list = data.get("items", [])
                        
                        if isinstance(items_list, list):
                            result = []
                            for item in items_list:
                                name = item.get("n")
                                price_rub = item.get("p", 0)
                                quantity = item.get("q", 0)
                                
                                if not name or price_rub <= 0:
                                    continue
                                
                                price_stars = max(1, int(price_rub / 1000 * 45))
                                price_usd = round(price_rub / 1000, 2)  # Добавлен расчёт USD
                                item_id = abs(hash(name)) % 1000000000
                                image = get_skin_image(name)
                                
                                result.append({
                                    "id": item_id,
                                    "name": name,
                                    "price_stars": price_stars,
                                    "price_usd": price_usd,  # Новое поле
                                    "image": image,
                                    "quantity": quantity
                                })
                            
                            all_items_cache = result
                            cache_timestamp = datetime.now()
                            print(f"Кэш обновлён! {len(all_items_cache)} предметов")
                        else:
                            print("Кэш не обновлён: items не список")
                    else:
                        print(f"Ошибка обновления кэша: статус {resp.status}")
        except Exception as e:
            print(f"Ошибка при обновлении кэша: {str(e)}")
        
        await sleep(CACHE_UPDATE_INTERVAL)


# Запуск фоновой задачи при старте приложения
@app.on_event("startup")
async def startup_event():
    create_task(update_items_cache())


# Эндпоинт с серверной фильтрацией и пагинацией по кэшу
@app.get("/api/items")
async def get_items(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(20, ge=5, le=50, description="Предметов на странице"),
    search: str = Query("", description="Поиск по названию предмета (подстрока)")
):
    if not all_items_cache:
        return {"items": [], "total": 0, "page": page, "pages": 1, "message": "Кэш ещё не загружен"}

    # Фильтрация по поисковому запросу
    filtered = all_items_cache
    if search.strip():
        search_lower = search.lower().strip()
        filtered = [
            item for item in all_items_cache
            if search_lower in item["name"].lower()
        ]

    # Пагинация по отфильтрованному списку
    start = (page - 1) * limit
    end = start + limit
    paginated = filtered[start:end]

    total = len(filtered)
    pages = (total + limit - 1) // limit if limit > 0 else 1

    return {
        "items": paginated,
        "total": total,
        "page": page,
        "pages": pages,
        "cache_timestamp": cache_timestamp.isoformat() if cache_timestamp else None
    }


@app.post("/api/create_invoice")
async def create_invoice(data: dict):
    item_id = data.get('item_id')
    user_id = data.get('user_id')
    price_stars = data.get('price_stars')

    if not all([item_id, user_id, price_stars]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    item_name = f"Предмет ID {item_id}"

    try:
        invoice_link = await bot(CreateInvoiceLink(
            title=f"Покупка: {item_name}",
            description="Скин CS2 из маркетплейса",
            payload=json.dumps({"item_id": item_id, "user_id": user_id}),
            provider_token="",
            currency="XTR",
            prices=[{"label": item_name, "amount": price_stars}]
        ))
        return {"invoice_link": invoice_link}
    except Exception as e:
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