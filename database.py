import asyncio
import json
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    telegram_id = Column(Integer, primary_key=True)  # Теперь PK, удалено отдельное id
    referrals = Column(Integer, default=0)
    items_received = Column(String)  # JSON-строка: '[{"name": "item1", "date": "2025-12-30"}]'
    steam_profile = Column(String)
    trade_link = Column(String)
    referred_by = Column(Integer, ForeignKey('users.telegram_id'))  # FK на telegram_id

engine = create_async_engine('sqlite+aiosqlite:///users.db')
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user(telegram_id: int, session: AsyncSession = None) -> User:
    if session:
        return await session.get(User, telegram_id)  # Теперь работает, т.к. PK = telegram_id
    async with async_session() as sess:
        return await sess.get(User, telegram_id)

async def add_user(telegram_id: int, referred_by: int = None):
    async with async_session() as sess:
        async with sess.begin():
            existing = await get_user(telegram_id, sess)
            if not existing:
                user = User(telegram_id=telegram_id, referred_by=referred_by)
                sess.add(user)

async def add_referral(referrer_id: int):
    async with async_session() as sess:
        async with sess.begin():
            user = await get_user(referrer_id, sess)
            if user:
                user.referrals += 1
                if user.referrals % 3 == 0:
                    # Заглушка для рандомного item (замени на API-запрос позже)
                    new_item = {"name": "Random CS2 Item", "date": "2025-12-30"}
                    items = json.loads(user.items_received) if user.items_received else []
                    items.append(new_item)
                    user.items_received = json.dumps(items)

async def update_steam(telegram_id: int, profile: str, trade_link: str):
    async with async_session() as sess:
        async with sess.begin():
            user = await get_user(telegram_id, sess)
            if user:
                user.steam_profile = profile
                user.trade_link = trade_link