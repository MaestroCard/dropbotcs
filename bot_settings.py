# bot_settings.py — глобальные переключатели бота (in-memory, сбрасываются при рестарте)

class BotSettings:
    gifts_enabled: bool = True   # True = выдача подарков включена

bot_settings = BotSettings()
