import hashlib
import hmac
import json
import random
import aiohttp
import os
from datetime import datetime
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import add_user, add_referral, update_steam, async_session, User, get_user
from keyboards import main_menu
from app import all_items_cache  # ← Импорт кэша предметов из app.py

# Настройки xpanda API (для отправки предмета после оплаты)
XPANDA_BASE_URL = "https://p2p.xpanda.pro/api/v1"
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
XPANDA_SECRET = os.getenv('XPANDA_SECRET', '')  # Если нужна подпись — добавь в .env

xpanda_headers = {
    "Authorization": XPANDA_API_KEY,
    "Content-Type": "application/json"
}

async def start_handler(message: types.Message):
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    user = await get_user(message.from_user.id)
    if not user:
        user = await add_user(message.from_user.id, ref_id)

    # ← здесь user уже точно не None

    if ref_id:
        await add_referral(ref_id)

    # Проверка на подарок
    if user.referrals >= 3 and not user.has_gift:
        # ... остальной код ...
        # Выбираем случайный предмет из самых дешёвых (топ-50 самых низких цен)
        cheap_items = sorted(all_items_cache, key=lambda x: x["price_stars"])[:50]
        if cheap_items:
            gift = random.choice(cheap_items)
            # Добавляем в инвентарь
            items = json.loads(user.items_received or "[]")
            items.append({
                "name": gift["name"],
                "price_stars": gift["price_stars"],
                "image": gift["image"],
                "date": datetime.now().isoformat()
            })
            user.items_received = json.dumps(items)
            user.has_gift = True
            await async_session.commit()

            await message.answer(f"🎉 Поздравляем! Вы пригласили 3 друзей и получаете подарок: **{gift['name']}** за {gift['price_stars']} ⭐!\n"
                                 f"Заберите его в профиле → кнопка «Забрать подарок».")
        else:
            await message.answer("Подарок не удалось выдать — предметов пока нет. Попробуйте позже.")

    # Клавиатура с кнопкой подарка, если он есть
    markup = main_menu()
    if user.has_gift:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")]
        ])

    await message.answer("Добро пожаловать в CS2 Marketplace! Откройте приложение:", reply_markup=markup)

# Обработчик callback-кнопки «Забрать подарок»
async def claim_gift_callback(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user or not user.has_gift:
        await callback.message.edit_text("Подарок уже забран или недоступен.")
        await callback.answer()
        return

    # Здесь можно добавить логику отправки предмета через xpanda (если нужно)
    # Пока просто отмечаем как полученный
    user.has_gift = False
    await async_session.commit()

    await callback.message.edit_text("🎁 Подарок успешно забран! Проверьте инвентарь в профиле.")
    await callback.message.edit_reply_markup(reply_markup=main_menu())
    await callback.answer("Подарок получен!")

async def bind_steam(message: types.Message):
    parts = message.text.split()
    if len(parts) == 3:
        await update_steam(message.from_user.id, parts[1], parts[2])
        await message.answer("Steam профиль привязан!")
    else:
        await message.answer("Используйте: /bind <steam_profile_url> <trade_link>")

async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

async def successful_payment_handler(message: types.Message):
    payload = json.loads(message.successful_payment.invoice_payload)
    item_id = payload['item_id']
    user_id = payload['user_id']

    # Получаем trade_link пользователя
    user = await get_user(user_id)
    if not user or not user.trade_link:
        await message.answer("Ошибка: Trade link не привязан в профиле!")
        return

    # Подготовка параметров для подписи и запроса
    params = {
        "product": str(item_id),  # ID предмета из xpanda
        "partner": "",  # Укажи свой partner ID, если есть
        "token": user.trade_link,  # Trade token покупателя
        "max_price": 1000,  # Максимальная цена в $ (можно динамически)
        "custom_id": str(message.from_user.id),  # Внутренний ID сделки
    }

    # Генерация строки для подписи (по твоему примеру)
    params_list = []
    for key in sorted(params.keys()):
        value = params[key]
        if isinstance(value, (dict, list)):
            continue
        if key in ['sign']:
            continue
        params_list.append(f"{key}:{value}")

    params_string = ';'.join(params_list)

    # Генерация подписи HMAC-SHA256
    sign = hmac.new(
        XPANDA_SECRET.encode(),
        params_string.encode(),
        hashlib.sha256
    ).hexdigest()

    # Добавляем sign в payload
    params["sign"] = sign

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{XPANDA_BASE_URL}/v1/purchases/",
                json=params,
                headers=xpanda_headers,
                timeout=30
            ) as resp:
                if resp.status in [200, 201]:
                    result = await resp.json()
                    await message.answer(f"⭐ Оплата прошла успешно! Предмет отправлен в трейд.\n"
                                         f"ID сделки в xpanda: {result.get('id', 'неизвестно')}\n"
                                         f"Проверьте Steam: {user.trade_link}")
                else:
                    error = await resp.text()
                    await message.answer(f"Оплата прошла, но ошибка отправки скина: {error}")
        except Exception as e:
            await message.answer(f"Ошибка связи с маркетплейсом: {str(e)}")

def register_handlers(dp: Dispatcher):
    dp.message.register(start_handler, Command(commands=['start']))
    dp.message.register(bind_steam, Command(commands=['bind']))
    dp.pre_checkout_query.register(pre_checkout_query_handler)
    dp.message.register(successful_payment_handler, lambda m: m.successful_payment is not None)
    dp.callback_query.register(claim_gift_callback, lambda c: c.data == "claim_gift")