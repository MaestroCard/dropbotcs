import asyncio
import uvicorn
from bot import dp, bot
from app import app
from cache import cache
from database import init_db

async def main():
    # Инициализация базы данных
    await init_db()
    print("База данных инициализирована")

    # Запуск обновления кэша предметов
    asyncio.create_task(cache.update())

    # Запуск Telegram-бота
    bot_task = asyncio.create_task(dp.start_polling(bot))

    # Запуск FastAPI сервера
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Запускаем всё параллельно
    await asyncio.gather(bot_task, server_task)

if __name__ == "__main__":
    asyncio.run(main())