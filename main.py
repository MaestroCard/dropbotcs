# main.py — только FastAPI + webhook (polling удалён)

import asyncio
import uvicorn
import os
from app import app
from cache import cache
from database import init_db

async def main():
    await init_db()
    print("База данных инициализирована")

    # Запуск обновления кэша
    asyncio.create_task(cache.update())

    # Запуск FastAPI сервера (он сам обрабатывает webhook)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())