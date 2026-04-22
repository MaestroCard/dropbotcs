# handlers.py

import hashlib
import hmac
import json
import random
import aiohttp
import asyncio
import os
import uuid
from datetime import datetime
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    add_user, add_referral, update_steam, async_session, User,
    get_user, get_all_users, freeze_user, get_users_for_review,
    admin_add_referral, approve_user,
)
from bot_settings import bot_settings
from sqlalchemy import select, func
from keyboards import main_menu
from cache import cache
from config import OWNER_ID, REFERRALS_FOR_GIFT, REFERRAL_REVIEW_THRESHOLD
from aiogram import Bot
from keyboards import gift_animation_keyboard

XPANDA_BASE_URL = "https://p2p.xpanda.pro/api/v1"
XPANDA_API_KEY = os.getenv('XPANDA_API_KEY')
XPANDA_SECRET = os.getenv('XPANDA_SECRET', '')
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
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


async def get_actual_balance():
    """Получает актуальный баланс напрямую с API"""
    url = f"{XPANDA_BASE_URL}/balance/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=xpanda_headers, timeout=10) as resp:
                if resp.status != 200:
                    print(f"[BALANCE CHECK] Ошибка статуса: {resp.status}")
                    return None
                data = await resp.json()
                available = data.get("available", 0)
                print(f"[BALANCE CHECK] Доступно: {available} руб")
                return available
    except Exception as e:
        print(f"[BALANCE CHECK ERROR] {type(e).__name__}: {str(e)}")
        return None


async def start_handler(message: types.Message):
    print(f"[START] Начало обработки от {message.from_user.id}, текст: {message.text}")
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    user = await get_user(message.from_user.id)
    is_new_user = user is None

    if is_new_user:
        user = await add_user(message.from_user.id)

    print(f"[DEBUG START] User {user.telegram_id}: referrals = {user.referrals}, has_gift = {user.has_gift}")

    if ref_id and is_new_user:
        try:
            print(f"[REFERRAL] Пытаемся добавить реферал {message.from_user.id} → от {ref_id}")
            result = await add_referral(ref_id, message.from_user.id)
            print(f"[REFERRAL] add_referral вернул: {result}")

            # Уведомление новому пользователю: инвайтер заморожен
            if result and result.get("inviter_frozen"):
                await message.answer(
                    "⚠️ Аккаунт пригласившего вас пользователя временно заморожен.\n"
                    "Ваш реферал сохранён и будет засчитан автоматически после проверки."
                )

            # Уведомление об авто-заморозке при достижении порога
            if result and result.get("needs_review_notification") and OWNER_ID:
                await message.bot.send_message(
                    OWNER_ID,
                    f"⚠️ <b>АВТО-ЗАМОРОЗКА</b>\n\n"
                    f"User ID: <code>{ref_id}</code>\n"
                    f"Достиг {REFERRAL_REVIEW_THRESHOLD} рефералов — заморожен и поставлен на проверку.\n\n"
                    f"Команды:\n"
                    f"/unfreeze {ref_id} — разморозить\n"
                    f"/freeze {ref_id} — оставить замороженным",
                    parse_mode="HTML",
                )

            if result and result.get("success"):
                inviter = await get_user(ref_id)
                if inviter:
                    print(f"[REFERRAL] У инвайтера {ref_id} referrals теперь = {inviter.referrals}")
                    if inviter.referrals >= REFERRALS_FOR_GIFT:
                        print("[REFERRAL] Отправляем уведомление о подарке инвайтеру")
                        markup = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")
                        ]])
                        await message.bot.send_message(
                            ref_id,
                            f"🎉 Поздравляем! Один из ваших рефералов присоединился — у вас теперь {inviter.referrals} рефералов!\n"
                            f"Нажмите кнопку ниже, чтобы получить подарок — случайный скин CS2.",
                            reply_markup=markup
                        )
                        print("[REFERRAL] Уведомление отправлено")
        except Exception as e:
            print(f"[REFERRAL CRASH] Ошибка при обработке реферала: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()

    markup = main_menu()
    await message.answer("Добро пожаловать в CS2 Marketplace! Откройте приложение:", reply_markup=markup)


async def claim_gift_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with async_session() as session:
        async with session.begin():
            user = await get_user(user_id, session)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return

            if not bot_settings.gifts_enabled:
                await callback.answer("Выдача подарков временно приостановлена. Попробуйте позже.", show_alert=True)
                return

            if user.is_frozen:
                await callback.answer("Ваш аккаунт заморожен. Получение подарков недоступно до окончания проверки.", show_alert=True)
                return

            if user.has_gift:
                await callback.answer("У вас уже есть один неполученный подарок. Сначала заберите его!", show_alert=True)
                return

            if user.referrals < REFERRALS_FOR_GIFT:
                await callback.answer("Недостаточно рефералов для подарка", show_alert=True)
                return

            if not user.trade_link:
                await callback.answer("Сначала привяжите trade-link в профиле", show_alert=True)
                return

            # Активируем подарок
            user.has_gift = True
            session.add(user)

    # Редактируем сообщение: меняем на web_app кнопку
    new_text = "Подарок активирован! Нажмите ниже, чтобы получить его!"
    new_markup = gift_animation_keyboard()  # Из keyboards.py

    await callback.message.edit_text(new_text, reply_markup=new_markup)
    await callback.answer("Подарок активирован!")

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

    actual_price_rub = None
    for item in cache.all_items:
        if item.get("product_id") == product_id or item.get("name") == product_id:
            actual_price_rub = item.get("price_rub")
            break

    if actual_price_rub is None:
        await message.answer("Ошибка: Не удалось найти актуальную цену предмета. Попробуйте позже.")
        return

    max_price = int(actual_price_rub * 1.2)

    params = {
        "product": product_id,
        "partner": trade_params["partner"],
        "token": trade_params["token"],
        "max_price": max_price,
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
    print(f"[DEBUG PAY] Использована цена: {actual_price_rub} руб (max_price = {max_price})")

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
                    # Конвертируем цену из миллидолларов в доллары
                    price_usd = actual_price_rub / 1000
                    await bot.send_message(OWNER_ID,
                        f"💰 УСПЕШНАЯ ПРОДАЖА (Stars)\n"
                        f"User ID: {user_id}\n"
                        f"Предмет: {product_id}\n"
                        f"Сумма: ${price_usd:.2f}\n"
                        f"ID сделки: {result.get('id', 'неизвестно')}\n"
                        f"Trade link: {user.trade_link}"
                    )
                else:
                    await message.answer(f"Оплата прошла, но ошибка отправки скина: {resp.status} — {text[:300]}")
        except Exception as e:
            await message.answer(f"Ошибка связи с маркетплейсом: {str(e)}")
            print(f"[ERROR PAY] {type(e).__name__}: {str(e)}")
            await bot.send_message(OWNER_ID,f"❌ Ошибка после оплаты\nUser: {user_id}\nПредмет: {product_id}\nОшибка: {str(e)}")

async def broadcast_command(message: types.Message):
    if message.chat.id != OWNER_ID:
        await message.answer("❌ У вас нет прав на эту команду.")
        return

    # ── Определяем фото и текст ───────────────────────────────────────
    photo_file_id = None

    if message.photo:
        # Сценарий 1: фото отправлено с подписью "/broadcast текст"
        photo_file_id = message.photo[-1].file_id
        raw = (message.caption or "").strip()
        text = raw[len("/broadcast"):].strip()
    elif message.reply_to_message and message.reply_to_message.photo:
        # Сценарий 2: reply на фото + "/broadcast текст" в тексте
        photo_file_id = message.reply_to_message.photo[-1].file_id
        raw = (message.text or "").strip()
        text = raw[len("/broadcast"):].strip()
    else:
        # Сценарий 3: только текст
        raw = (message.text or "").strip()
        text = raw[len("/broadcast"):].strip()

    if not text and not photo_file_id:
        await message.answer(
            "⚠️ Укажите текст рассылки после команды.\n\n"
            "Варианты:\n"
            "• <code>/broadcast Текст сообщения</code> — текст\n"
            "• Отправить фото с подписью <code>/broadcast Текст</code> — фото + текст\n"
            "• Ответить (reply) на фото командой <code>/broadcast Текст</code> — фото + текст",
            parse_mode="HTML",
        )
        return

    kind = "с фото" if photo_file_id else "текстовая"
    preview = text[:100] + ("..." if len(text) > 100 else "")
    await message.answer(f"🚀 Начинаю рассылку ({kind}):\n\n{preview}\n\nПодождите, считаю пользователей...")

    users = await get_all_users()
    total = len(users)
    sent = 0
    failed = 0

    await message.answer(f"Найдено пользователей: {total}. Начинаю отправку...")

    for i, user in enumerate(users, 1):
        try:
            markup = main_menu()
            if photo_file_id:
                await bot.send_photo(
                    user.telegram_id,
                    photo=photo_file_id,
                    caption=text or None,
                    reply_markup=markup,
                )
            else:
                await bot.send_message(user.telegram_id, text, reply_markup=markup)
            sent += 1
        except Exception as e:
            print(f"[BROADCAST] Ошибка отправки {user.telegram_id}: {str(e)}")
            failed += 1

        # Защита от лимитов Telegram (~30 сообщений/сек)
        if i % 30 == 0:
            await asyncio.sleep(1)

        if i % 100 == 0:
            await message.answer(f"Обработано {i}/{total}...")

    await message.answer(f"✅ Рассылка завершена!\nУспешно: {sent}\nОшибок: {failed}")

async def reset_gifts_command(message: types.Message):
    """Сбрасывает has_gift=False у всех пользователей (для миграции на новую механику)"""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ У вас нет прав на эту команду.")
        return
    
    from sqlalchemy import update
    from database import async_session, User
    
    await message.answer("🔄 Сбрасываю has_gift у всех пользователей...")
    
    try:
        async with async_session() as session:
            result = await session.execute(
                update(User).values(has_gift=False)
            )
            await session.commit()
            count = result.rowcount
            
        await message.answer(f"✅ Готово! Сброшено записей: {count}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

async def stats_command(message: types.Message):
    """Показывает статистику бота (только для владельца)"""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ У вас нет прав на эту команду.")
        return
    
    from sqlalchemy import func
    from database import async_session, User
    
    try:
        async with async_session() as session:
            # Общее количество пользователей
            total_users = await session.scalar(select(func.count(User.telegram_id)))
            
            # Количество с привязанным trade_link
            with_trade = await session.scalar(
                select(func.count(User.telegram_id)).where(User.trade_link != None)
            )
            
            # Количество с активными подарками
            with_gift = await session.scalar(
                select(func.count(User.telegram_id)).where(User.has_gift == True)
            )
            
            # Сумма рефералов
            total_referrals = await session.scalar(select(func.sum(User.referrals)))
            
        stats_text = (
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{total_users}</b>\n"
            f"🔗 С привязанным Steam: <b>{with_trade}</b>\n"
            f"🎁 С активными подарками: <b>{with_gift}</b>\n"
            f"📈 Всего рефералов: <b>{total_referrals or 0}</b>"
        )
        
        await message.answer(stats_text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка получения статистики: {str(e)}")

async def promo_gift_command(message: types.Message):
    """Массовая рассылка с кнопкой активации подарка (только для владельца)"""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ У вас нет прав на эту команду.")
        return
    
    # Получаем текст после команды
    text = message.text[len("/promo_gift"):].strip()
    if not text:
        text = "🎁 Специальное предложение! У вас есть подарок — случайный скин CS2!"
    
    await message.answer(f"🚀 Начинаю рассылку...\n\nТекст:\n{text}")
    
    users = await get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    
    # Кнопка для активации подарка (не webapp!)
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Получить подарок 🎁", callback_data="promo_claim")
    ]])
    
    for i, user in enumerate(users, 1):
        try:
            await bot.send_message(
                user.telegram_id,
                text,
                reply_markup=markup
            )
            sent += 1
        except Exception as e:
            print(f"[PROMO GIFT] Ошибка отправки {user.telegram_id}: {str(e)}")
            failed += 1
        
        # Защита от лимитов
        if i % 30 == 0:
            await asyncio.sleep(1)
        
        if i % 100 == 0:
            await message.answer(f"Обработано {i}/{total}...")
    
    await message.answer(f"✅ Рассылка завершена!\nУспешно: {sent}\nОшибок: {failed}")


async def promo_claim_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку 'Получить подарок' из promo рассылки"""
    user_id = callback.from_user.id
    async with async_session() as session:
        async with session.begin():
            user = await get_user(user_id, session)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return

            if user.has_gift:
                await callback.answer("У вас уже есть неполученный подарок. Сначала заберите его!", show_alert=True)
                return

            if not user.trade_link:
                await callback.answer("Сначала привяжите trade-link в профиле", show_alert=True)
                return

            # Активируем подарок
            user.has_gift = True
            session.add(user)

    # Меняем на кнопку WebApp для получения подарка
    new_text = "🎉 Подарок активирован! Нажмите ниже, чтобы получить его!"
    new_markup = gift_animation_keyboard()

    await callback.message.edit_text(new_text, reply_markup=new_markup)
    await callback.answer("Подарок активирован!")

async def gifts_off_command(message: types.Message):
    if message.chat.id != OWNER_ID:
        await message.answer("❌ Нет прав.")
        return
    bot_settings.gifts_enabled = False
    await message.answer("⛔ Выдача подарков остановлена.")


async def gifts_on_command(message: types.Message):
    if message.chat.id != OWNER_ID:
        await message.answer("❌ Нет прав.")
        return
    bot_settings.gifts_enabled = True
    await message.answer("✅ Выдача подарков включена.")


async def freeze_command(message: types.Message):
    """Заморозить пользователя по Telegram ID (только для владельца)."""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ Нет прав.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /freeze <telegram_id>")
        return
    target_id = int(parts[1])
    ok = await freeze_user(target_id, freeze=True)
    if ok:
        await message.answer(f"✅ Пользователь <code>{target_id}</code> заморожен.", parse_mode="HTML")
        try:
            await bot.send_message(
                target_id,
                "⚠️ Ваш реферальный аккаунт временно заморожен.\n"
                "Новые рефералы не будут засчитываться до окончания проверки.\n"
                "Ранее приглашённые вами пользователи сохранены и будут восстановлены автоматически.",
            )
        except Exception:
            pass
    else:
        await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден.", parse_mode="HTML")


async def unfreeze_command(message: types.Message):
    """Разморозить пользователя по Telegram ID (только для владельца)."""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ Нет прав.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /unfreeze <telegram_id>")
        return
    target_id = int(parts[1])
    result = await approve_user(target_id)
    if result["ok"]:
        restored = result["restored"]
        await message.answer(
            f"✅ Пользователь <code>{target_id}</code> разморожен.\n"
            f"Восстановлено рефералов: <b>+{restored}</b> ({result['referrals_before']} → {result['referrals_after']})",
            parse_mode="HTML",
        )
        # Уведомить пользователя о разморозке
        try:
            await bot.send_message(
                target_id,
                "✅ Ваш реферальный аккаунт разморожен!\n"
                "Все рефералы восстановлены, новые снова засчитываются.",
            )
        except Exception:
            pass
        # Отправить уведомления о подарках за восстановленных рефералов
        if restored > 0:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Забрать подарок 🎁", callback_data="claim_gift")
            ]])
            for i in range(restored):
                try:
                    await bot.send_message(
                        target_id,
                        f"🎉 Один из ваших рефералов был засчитан после проверки аккаунта!\n"
                        f"У вас теперь <b>{result['referrals_before'] + i + 1}</b> рефералов.\n"
                        f"Нажмите кнопку ниже, чтобы получить подарок — случайный скин CS2.",
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"[UNFREEZE GIFT NOTIFY] {e}")
    else:
        await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден.", parse_mode="HTML")


async def review_list_command(message: types.Message):
    """Показать список пользователей на ручной проверке (только для владельца)."""
    if message.chat.id != OWNER_ID:
        await message.answer("❌ Нет прав.")
        return
    users = await get_users_for_review()
    if not users:
        await message.answer("✅ Нет пользователей на проверке.")
        return
    lines = [f"📋 <b>На проверке: {len(users)}</b>\n"]
    for u in users[:20]:
        status = "🔴 заморожен" if u.is_frozen else "🟡 активен"
        lines.append(f"• <code>{u.telegram_id}</code> — {u.referrals} реф. — {status}")
    if len(users) > 20:
        lines.append(f"\n...и ещё {len(users) - 20}. Смотрите полный список в веб-панели.")
    await message.answer("\n".join(lines), parse_mode="HTML")


def register_handlers(dp: Dispatcher):
    dp.message.register(start_handler, Command(commands=['start']))
    dp.message.register(bind_steam, Command(commands=['bind']))
    dp.message.register(broadcast_command, Command(commands=['broadcast']))
    # Фото с подписью /broadcast ... или reply на фото с командой /broadcast
    dp.message.register(
        broadcast_command,
        lambda m: m.photo and m.caption and m.caption.lstrip().startswith('/broadcast')
    )
    dp.message.register(reset_gifts_command, Command(commands=['reset_gifts']))
    dp.message.register(stats_command, Command(commands=['stats']))
    dp.message.register(promo_gift_command, Command(commands=['promo_gift']))
    dp.message.register(gifts_off_command, Command(commands=['gifts_off']))
    dp.message.register(gifts_on_command,  Command(commands=['gifts_on']))
    dp.message.register(freeze_command, Command(commands=['freeze']))
    dp.message.register(unfreeze_command, Command(commands=['unfreeze']))
    dp.message.register(review_list_command, Command(commands=['review_list']))
    dp.pre_checkout_query.register(pre_checkout_query_handler)
    dp.message.register(successful_payment_handler, lambda m: m.successful_payment is not None)
    dp.callback_query.register(claim_gift_callback, lambda c: c.data == "claim_gift")
    dp.callback_query.register(promo_claim_callback, lambda c: c.data == "promo_claim")