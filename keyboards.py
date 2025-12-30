from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="Открыть приложение",  # Добавлен text=
        web_app=WebAppInfo(url="https://fleta-electrometallurgical-repercussively.ngrok-free.dev/web_app/index.html")  # Замени на серверный URL позже
    ))
    builder.adjust(1)  # Кнопки в один столбец
    return builder.as_markup()