# keyboards.py

import os
from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_webapp_url() -> str:
    """
    Формирует полный URL для Telegram Web App на основе переменной RAILWAY_PUBLIC_DOMAIN
    """
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    
    if not domain:
        # fallback на случай, если переменная не задана (локальная разработка / отладка)
        domain = "localhost:8000"  # или другой дефолт, например ngrok
        protocol = "http"
    else:
        protocol = "https"

    # Формируем полный путь
    return f"{protocol}://{domain}/web_app/index.html"


def main_menu():
    builder = InlineKeyboardBuilder()
    
    webapp_url = get_webapp_url()
    
    builder.add(InlineKeyboardButton(
        text="Открыть приложение",
        web_app=WebAppInfo(url=webapp_url)
    ))
    
    builder.adjust(1)
    return builder.as_markup()