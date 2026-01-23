import asyncio
import json
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    referred_by = Column(Integer, ForeignKey('users.telegram_id'), nullable=True)
    referrals = Column(Integer, default=0)
    items_received = Column(String, default="[]")
    steam_profile = Column(String, nullable=True)
    trade_link = Column(String, nullable=True)
    has_gift = Column(Boolean, default=False)
    gift_item = Column(String, nullable=True)

engine = create_async_engine('sqlite+aiosqlite:///users.db', echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user(telegram_id: int, session: AsyncSession = None) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    if session:
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async with async_session() as sess:
        result = await sess.execute(stmt)
        return result.scalar_one_or_none()

async def add_user(telegram_id: int, referred_by: int = None) -> User:
    async with async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                print(f"Пользователь {telegram_id} уже существует")
                return user

            user = User(
                telegram_id=telegram_id,
                referred_by=referred_by
            )
            session.add(user)

        print(f"Добавлен новый пользователь: {telegram_id}, приглашён {referred_by}")
        return user

async def add_referral(referrer_telegram_id: int):
    async with async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == referrer_telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                user.referrals += 1
                print(f"У пользователя {referrer_telegram_id} теперь {user.referrals} рефералов")
            else:
                print(f"Пригласивший {referrer_telegram_id} не найден")

async def update_steam(telegram_id: int, profile: str, trade_link: str):
    async with async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                user.steam_profile = profile
                user.trade_link = trade_link
                print(f"Обновлены Steam данные для {telegram_id}")
            else:
                print(f"Пользователь {telegram_id} не найден")