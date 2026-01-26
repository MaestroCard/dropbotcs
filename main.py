# main.py — теперь с webhook

import asyncio
import uvicorn
import os
from bot import dp, bot
from app import app
from cache import cache
from database import init_db

async def main():
    # Инициализация базы данных
    await init_db()
    print("База данных инициализирована")

    # Запуск обновления кэша
    asyncio.create_task(cache.update())

    # Установка webhook
    webhook_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/webhook"  # Railway сам даёт домен
    webhook_secret = os.getenv("WEBHOOK_SECRET", "your-very-long-secret-token")  # придумай длинный секрет

    await bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        drop_pending_updates=True  # очистить очередь старых сообщений
    )
    print(f"Webhook установлен: {webhook_url}")

    # Запуск FastAPI сервера (он будет обрабатывать /webhook)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())