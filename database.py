# database.py — PostgreSQL + asyncpg (без psycopg2)

import asyncio
import json
import os
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, BigInteger, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не найден в .env! Добавьте строку вида: postgresql+asyncpg://user:pass@host:port/dbname")

# Явно указываем asyncpg-драйвер
if "postgresql://" in DATABASE_URL and "postgresql+asyncpg://" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    print("Автоматически добавлен +asyncpg в DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    referred_by = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=True)
    referrals = Column(Integer, default=0)
    items_received = Column(String, default="[]")
    steam_profile = Column(String, nullable=True)
    trade_link = Column(String, nullable=True)
    has_gift = Column(Boolean, default=False)
    gift_item = Column(String, nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("База данных PostgreSQL инициализирована и таблицы созданы")

async def get_user(telegram_id: int, session: AsyncSession = None) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    if session:
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async with async_session() as sess:
        result = await sess.execute(stmt)
        return result.scalar_one_or_none()

# ────────────────────────────────────────────────
# Изменено: теперь НЕ принимает referred_by
# ────────────────────────────────────────────────
async def add_user(telegram_id: int) -> User:
    async with async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                print(f"Пользователь {telegram_id} уже существует")
                return user

            user = User(telegram_id=telegram_id)  # referred_by остаётся None
            session.add(user)

        print(f"Добавлен новый пользователь: {telegram_id}")
        return user

# ────────────────────────────────────────────────
# add_referral — остаётся почти без изменений,
# но теперь именно он отвечает за установку referred_by
# ────────────────────────────────────────────────
async def add_referral(referrer_telegram_id: int, invited_telegram_id: int):
    if referrer_telegram_id == invited_telegram_id:
        print(f"[WARNING] Самореферал {invited_telegram_id} — игнорируем")
        return

    async with async_session() as session:
        async with session.begin():
            stmt_inviter = select(User).where(User.telegram_id == referrer_telegram_id)
            result_inviter = await session.execute(stmt_inviter)
            inviter = result_inviter.scalar_one_or_none()

            stmt_invited = select(User).where(User.telegram_id == invited_telegram_id)
            result_invited = await session.execute(stmt_invited)
            invited = result_invited.scalar_one_or_none()

            if not inviter or not invited:
                print(f"Не найден inviter ({referrer_telegram_id}) или invited ({invited_telegram_id})")
                return

            if invited.referred_by is not None:
                if invited.referred_by == referrer_telegram_id:
                    print(f"[INFO] Повторное приглашение {invited_telegram_id} от {referrer_telegram_id} — игнорируем")
                    return
                else:
                    print(f"[WARNING] Конфликт: {invited_telegram_id} уже приглашён {invited.referred_by}, а теперь пытаются {referrer_telegram_id}")
                    return

            # Устанавливаем связь и увеличиваем счётчик
            invited.referred_by = referrer_telegram_id
            inviter.referrals += 1

            await session.refresh(inviter)
            await session.refresh(invited)

            print(f"[SUCCESS] Добавлен реферал: {invited_telegram_id} → {referrer_telegram_id}")
            print(f"У {referrer_telegram_id} теперь referrals = {inviter.referrals}")

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