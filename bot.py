import logging
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os
from handlers import register_handlers

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

# ←←← НОВОЕ ←←←
OWNER_ID = os.getenv('OWNER_ID')
if OWNER_ID:
    OWNER_ID = int(OWNER_ID)
else:
    OWNER_ID = None
    print("OWNER_ID не указан в .env — уведомления владельцу отключены")

async def notify_owner(text: str):
    """Отправляет сообщение владельцу бота (если OWNER_ID указан)"""
    if OWNER_ID:
        try:
            await bot.send_message(chat_id=OWNER_ID, text=text[:4000], disable_web_page_preview=True)
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление владельцу ({OWNER_ID}): {e}")
# ←←← КОНЕЦ НОВОГО ←←←

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

register_handlers(dp)