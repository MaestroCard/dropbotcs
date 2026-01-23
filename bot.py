import logging
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
import os
from handlers import register_handlers

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

register_handlers(dp)