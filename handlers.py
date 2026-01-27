# handlers.py

import hashlib
import hmac
import json
import random
import aiohttp
import os
import uuid
from datetime import datetime
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import add_user, add_referral, update_steam, async_session, User, get_user
from keyboards import main_menu
from cache import cache

XPANDA_BASE_URL = "https://p2p.xpanda.pro/api/v1"
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
XPANDA_SECRET = os.getenv('XPANDA_SECRET', '')

xpanda_headers = {
    "Authorization": XPANDA_API_KEY,
    "Content-Type": "application/json"
}


def parse_trade_link(trade_link: str) -> dict | None:
    if not trade_link:
        return None

    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(trade_link)
        params = parse_qs(parsed.query)

        partner = params.get('partner', [None])[0]
        token = params.get('token', [None])[0]

        if partner and token:
            return {
                "partner": partner,
                "token": token
            }
        else:
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка парсинга trade-link: {e}")
        return None


async def start_handler(message: types.Message):
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    user = await get_user(message.from_user.id)
    created = False
    if not user:
        user = await add_user(message.from_user.id, ref_id)
        created = True

    print(f"[DEBUG START] User {user.telegram_id}: "
          f"referrals = {user.referrals}, "
          f"has_gift = {user.has_gift}, "
          f"кэш предметов = {len(cache.all_items)} шт")

    if ref_id and created:
        # Передаём ID приглашённого (message.from_user.id)
        await add_referral(ref_id, message.from_user.id)

        # Проверяем пригласившего после добавления
        inviter = await get_user(ref_id)
        if inviter and inviter.referrals >= 3 and not inviter.has_gift:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")]
            ])

            await message.bot.send_message(
                ref_id,
                f"🎉 Поздравляем! Один из ваших рефералов присоединился — у вас теперь {inviter.referrals} рефералов!\n"
                f"Вы получаете подарок. Нажмите кнопку ниже, чтобы получить рандомный дешёвый скин в Steam.",
                reply_markup=markup
            )

    markup = main_menu()
    await message.answer("Добро пожаловать в CS2 Marketplace! Откройте приложение:", reply_markup=markup)

async def claim_gift_callback(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user.has_gift:
        await callback.answer("Подарок уже получен!", show_alert=True)
        return

    if user.referrals < 3:
        await callback.answer("У вас ещё недостаточно рефералов!", show_alert=True)
        return

    if not user.trade_link:
        await callback.answer("Сначала привяжите trade link в профиле!", show_alert=True)
        return

    trade_params = parse_trade_link(user.trade_link)
    if not trade_params:
        await callback.answer("Неверный формат trade-ссылки. Проверьте ссылку в профиле!", show_alert=True)
        return

    cheap_items = sorted(cache.all_items, key=lambda x: x["price_stars"])[:int(os.getenv("CHEAP_ITEMS_COUNT", 5))]
    if not cheap_items:
        await callback.answer("Подарков пока нет. Попробуйте позже!", show_alert=True)
        return

    gift = random.choice(cheap_items)

    custom_id = f"gift_{user.telegram_id}_{uuid.uuid4().hex[:8]}"

    params = {
        "product": gift['product_id'],
        "partner": trade_params["partner"],
        "token": trade_params["token"],
        "max_price": 1000,
        "custom_id": custom_id,
    }

    params_list = [f"{k}:{v}" for k, v in sorted(params.items()) if v is not None]
    params_string = ';'.join(params_list)

    sign = hmac.new(
        XPANDA_SECRET.encode(),
        params_string.encode(),
        hashlib.sha256
    ).hexdigest()

    params["sign"] = sign

    url = f"{XPANDA_BASE_URL}/purchases/"

    print(f"[DEBUG GIFT] Отправка подарка на: {url}")
    print(f"[DEBUG GIFT] Payload: {json.dumps(params, indent=2, ensure_ascii=False)}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                json=params,
                headers=xpanda_headers,
                timeout=30
            ) as resp:
                text = await resp.text()
                print(f"[DEBUG GIFT] Статус: {resp.status}, Ответ: {text[:500]}...")

                if resp.status in [200, 201]:
                    user.has_gift = True
                    async with async_session() as session:
                        async with session.begin():
                            session.add(user)

                    await callback.message.edit_text(
                        f"🎉 Подарок успешно отправлен в Steam!\n"
                        f"**{gift['name']}** за {gift['price_stars']} ⭐\n"
                        f"Проверьте трейд-офер в Steam."
                    )
                    await callback.answer("Подарок получен!", show_alert=True)
                else:
                    await callback.answer(f"Ошибка отправки: {resp.status} — {text[:200]}", show_alert=True)
        except Exception as e:
            await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


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
    product_id = payload.get('product_id')
    user_id = payload['user_id']

    user = await get_user(user_id)
    if not user or not user.trade_link:
        await message.answer("Ошибка: Trade link не привязан в профиле!")
        return

    trade_params = parse_trade_link(user.trade_link)
    if not trade_params:
        await message.answer("Ошибка: Неверный формат trade-ссылки. Проверьте ссылку в профиле.")
        return

    params = {
        "product": product_id,
        "partner": trade_params["partner"],
        "token": trade_params["token"],
        "max_price": 1000,
        "custom_id": f"purchase_{user.telegram_id}_{uuid.uuid4().hex[:8]}",
    }

    params_list = [f"{k}:{v}" for k, v in sorted(params.items()) if v is not None]
    params_string = ';'.join(params_list)

    sign = hmac.new(
        XPANDA_SECRET.encode(),
        params_string.encode(),
        hashlib.sha256
    ).hexdigest()

    params["sign"] = sign

    url = f"{XPANDA_BASE_URL}/purchases/"

    print(f"[DEBUG PAY] Отправка на: {url}")
    print(f"[DEBUG PAY] Payload: {json.dumps(params, indent=2, ensure_ascii=False)}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                json=params,
                headers=xpanda_headers,
                timeout=30
            ) as resp:
                text = await resp.text()
                print(f"[DEBUG PAY] Статус: {resp.status}, Ответ: {text[:500]}...")

                if resp.status in [200, 201]:
                    result = json.loads(text)
                    await message.answer(
                        f"⭐ Оплата прошла успешно! Предмет отправлен в трейд.\n"
                        f"ID сделки: {result.get('id', 'неизвестно')}\n"
                        f"Проверьте Steam: {user.trade_link}"
                    )
                else:
                    await message.answer(f"Оплата прошла, но ошибка отправки скина: {resp.status} — {text[:300]}")
        except Exception as e:
            await message.answer(f"Ошибка связи с маркетплейсом: {str(e)}")
            print(f"[ERROR PAY] {type(e).__name__}: {str(e)}")


def register_handlers(dp: Dispatcher):
    dp.message.register(start_handler, Command(commands=['start']))
    dp.message.register(bind_steam, Command(commands=['bind']))
    dp.pre_checkout_query.register(pre_checkout_query_handler)
    dp.message.register(successful_payment_handler, lambda m: m.successful_payment is not None)
    dp.callback_query.register(claim_gift_callback, lambda c: c.data == "claim_gift")