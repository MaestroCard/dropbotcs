# main.py — полный, с правильным PORT

import asyncio
import uvicorn
import os
from app import app
from cache import cache
from database import init_db

async def main():
    await init_db()
    print("База данных инициализирована")

    asyncio.create_task(cache.update())

    port = int(os.getenv("PORT", 8000))  # Railway требует PORT
    print(f"Запуск сервера на порту {port}")

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())