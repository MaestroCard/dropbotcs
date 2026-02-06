# cache.py — синглтон для общего кэша предметов

from datetime import datetime
import asyncio
import aiohttp
import os
import json
from dotenv import load_dotenv
from config import OWNER_ID
from aiogram import Bot

load_dotenv()

XPANDA_BASE_URL = "https://p2p.xpanda.pro/api/v1"
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
xpanda_headers = {
    "Authorization": XPANDA_API_KEY,
    "Content-Type": "application/json"
}

class ItemsCache:
    _instance = None
    _ip_logged = False  # флаг, чтобы логировать IP только один раз
    _cache_not_getted = True

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ItemsCache, cls).__new__(cls)
            cls._instance.all_items = []
            cls._instance.cache_timestamp = None
            cls._instance.CACHE_UPDATE_INTERVAL = int(os.getenv("CACHE_UPDATE_INTERVAL", 300))
        return cls._instance

    def __init__(self):
        # Загрузка изображений (только один раз)
        self.skins_data = []
        self.crates_data = []
        self.stickers_data = []
        self.balance = {
            "total": 0,
            "locked": 0,
            "available": 0
        }
        self.balance_last_updated = None

        try:
            with open('data/skins.json', 'r', encoding='utf-8') as f:
                self.skins_data = json.load(f)
        except FileNotFoundError:
            print("skins.json не найден")

        try:
            with open('data/crates.json', 'r', encoding='utf-8') as f:
                self.crates_data = json.load(f)
        except FileNotFoundError:
            print("crates.json не найден")

        try:
            with open('data/stickers.json', 'r', encoding='utf-8') as f:
                self.stickers_data = json.load(f)
        except FileNotFoundError:
            print("stickers.json не найден")

    async def update_balance(self):
        """Обновляет только баланс"""
        url = XPANDA_BASE_URL + "/balance/"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=xpanda_headers,
                    timeout=15
                ) as resp:
                    if resp.status != 200:
                        print(f"[BALANCE] Ошибка статуса: {resp.status}")
                        return False
                    
                    data = await resp.json()
                    self.balance = {
                        "total": data.get("total", 0),
                        "locked": data.get("locked", 0),
                        "available": data.get("available", 0)
                    }
                    self.balance_last_updated = datetime.now()
                    print(f"[BALANCE] Обновлён: available = {self.balance['available']}")
                    return True
        except Exception as e:
            print(f"[BALANCE ERROR] {type(e).__name__}: {str(e)}")
            await bot.send_message(OWNER_ID,f"❌ Ошибка обновления баланса XPANDA:\n{type(e).__name__}: {str(e)}")
            return False
    
    def get_skin_image(self, name: str) -> str:
        name_lower = name.lower().strip()
        cleaned_name = name_lower.replace('stattrak™ ', '').split('(')[0].strip()
        cleaned_name = cleaned_name.replace('souvenir ', '').split('(')[0].strip()

        for skin in self.skins_data:
            if cleaned_name in skin.get('name', '').lower() or cleaned_name in skin.get('market_hash_name', '').lower():
                if img := skin.get('image'):
                    return img

        for crate in self.crates_data:
            if name_lower == crate.get('name', '').lower() or cleaned_name in crate.get('name', '').lower():
                if img := crate.get('image'):
                    return img

        for sticker in self.stickers_data:
            if cleaned_name in sticker.get('name', '').lower() or name_lower in sticker.get('name', '').lower():
                if img := sticker.get('image'):
                    return img

        return f"https://via.placeholder.com/80x60?text={name[:20].replace(' ', '+')}"

    async def update(self):
        while True:
            if self._cache_not_getted:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] → Обновление кэша предметов...")
                

            # Получаем IP сервера один раз (4-й способ)
            if not self._ip_logged:
                try:
                    async with aiohttp.ClientSession() as temp_session:
                        async with temp_session.get("https://api.ipify.org") as resp:
                            server_ip = await resp.text()
                            print(f"[DEBUG IP] Исходящий IP сервера: {server_ip}")
                            bot.send_message(OWNER_ID,f"[DEBUG IP] Исходящий IP сервера: {server_ip}")
                            self._ip_logged = True  # больше не логируем
                except Exception as e:
                    print(f"[DEBUG IP] Ошибка получения IP: {str(e)}")

            try:
                url = XPANDA_BASE_URL + "/items/prices/"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=xpanda_headers, timeout=45) as resp:
                        if resp.status != 200:
                            if self._cache_not_getted:
                                print(f"   Ошибка: статус {resp.status}")
                                self._cache_not_getted = False
                            continue
                        self._cache_not_getted = True
                        data = await resp.json()
                        items_list = data.get("items", [])

                        if not isinstance(items_list, list):
                            print("   'items' не список")
                            continue

                        result = []
                        skipped = 0

                        for item in items_list:
                            name = item.get("n")
                            price_rub = item.get("p", 0)
                            quantity = item.get("q", 0)

                            if not name or price_rub <= 0:
                                skipped += 1
                                continue

                            price_stars = max(1, int(price_rub / 1000 * int(os.getenv("DOLAR_TO_STARS", 45))))
                            price_usd = round(price_rub / 1000, 2)

                            item_id = abs(hash(name)) % 1000000000
                            product_id = name

                            image = self.get_skin_image(name)

                            result.append({
                                "id": item_id,
                                "product_id": product_id,
                                "name": name,
                                "price_stars": price_stars,
                                "price_usd": price_usd,
                                "price_rub": price_rub,
                                "image": image,
                                "quantity": quantity
                            })

                        self.all_items = result
                        self.cache_timestamp = datetime.now()
                        print(f"   Кэш обновлён! {len(result)} предметов (пропущено: {skipped})")
                        self._cache_not_getted = True
                        print(f"   Пример первого предмета: {result[0] if result else 'пусто'}")

            except Exception as e:
                if self._cache_not_getted:
                    print(f"   Ошибка обновления кэша: {type(e).__name__}: {str(e)}")
                    self._cache_not_getted = False
                await bot.send_message(OWNER_ID,f"❌ Ошибка обновления кэша предметов:\n{type(e).__name__}: {str(e)}")

            await self.update_balance()
            await asyncio.sleep(self.CACHE_UPDATE_INTERVAL)


# Глобальный экземпляр кэша (синглтон)
cache = ItemsCache()