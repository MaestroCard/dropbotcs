import json
from aiogram import Dispatcher, types
from aiogram.filters import Command
from database import add_user, add_referral, update_steam, async_session, User, get_user
from keyboards import main_menu

async def start_handler(message: types.Message):
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    await add_user(message.from_user.id, ref_id)
    if ref_id:
        await add_referral(ref_id)
    await message.answer("Добро пожаловать в CS2 Marketplace! Откройте приложение:", reply_markup=main_menu())

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
    # Здесь интегрируй твой API для выдачи реального item
    # Пример: await aiohttp.post('your_api/issue_item', data={'user': user_id, 'item': item_id})
    async with async_session() as sess:
        async with sess.begin():
            user = await get_user(user_id, sess)
            if user:
                items = json.loads(user.items_received) if user.items_received else []
                items.append({"name": f"Item {item_id}", "date": "2025-12-30"})  # Замени на реальный
                user.items_received = json.dumps(items)
    await message.answer("Оплата успешна! Предмет выдан.")

def register_handlers(dp: Dispatcher):
    dp.message.register(start_handler, Command(commands=['start']))
    dp.message.register(bind_steam, Command(commands=['bind']))
    dp.pre_checkout_query.register(pre_checkout_query_handler)
    dp.message.register(successful_payment_handler, lambda m: m.successful_payment is not None)