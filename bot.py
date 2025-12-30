import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from database import init_db
from handlers import register_handlers

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

register_handlers(dp)

async def main():
    await init_db()  # Инициализация БД
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())