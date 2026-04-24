# database.py — PostgreSQL + asyncpg (без psycopg2)

import asyncio
import datetime
import json
import os
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, BigInteger, DateTime, select, text, func
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
    id           = Column(Integer, primary_key=True)
    telegram_id  = Column(BigInteger, unique=True, nullable=False)
    referred_by  = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=True)
    referrals    = Column(Integer, default=0)
    items_received = Column(String, default="[]")
    steam_profile  = Column(String, nullable=True)
    trade_link     = Column(String, nullable=True)
    has_gift       = Column(Boolean, default=False)
    gift_item      = Column(String, nullable=True)
    # --- новые колонки ---
    is_frozen         = Column(Boolean, default=False, nullable=True)
    needs_review      = Column(Boolean, default=False, nullable=True)
    joined_at         = Column(DateTime, nullable=True)
    frozen_referrals  = Column(Integer, default=0, nullable=True)   # рефералы во время заморозки
    webapp_opened     = Column(Boolean, default=False, nullable=True) # открыл ли WebApp хоть раз
    registration_ip   = Column(String,  nullable=True)               # IP при первом открытии WebApp
    referral_pending  = Column(Boolean, default=False, nullable=True) # реферал зафиксирован, но ещё не засчитан


async def run_migrations():
    """Безопасно добавляет новые колонки к существующим таблицам (идемпотентно)."""
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_frozen         BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS needs_review      BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_at         TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS frozen_referrals  INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS webapp_opened     BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_ip   VARCHAR(45)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_pending  BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            await conn.execute(text(sql))
    print("Миграции применены")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations()
    print("База данных PostgreSQL инициализирована и таблицы созданы")


async def get_user(telegram_id: int, session: AsyncSession = None) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    if session:
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async with async_session() as sess:
        result = await sess.execute(stmt)
        return result.scalar_one_or_none()


async def add_user(telegram_id: int) -> User:
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
                joined_at=datetime.datetime.utcnow(),
            )
            session.add(user)

        print(f"Добавлен новый пользователь: {telegram_id}")
        return user


async def add_referral(referrer_telegram_id: int, invited_telegram_id: int) -> dict:
    """
    Фиксирует реферальную связь. Счётчик НЕ инкрементируется сразу —
    реферал засчитывается только после того, как приглашённый откроет WebApp
    (см. mark_webapp_opened). Это защита от ботов и купленных аккаунтов.

    Возвращает: success, inviter_frozen
    """
    if referrer_telegram_id == invited_telegram_id:
        print(f"[WARNING] Самореферал {invited_telegram_id} — игнорируем")
        return {"success": False, "inviter_frozen": False}

    async with async_session() as session:
        async with session.begin():
            inviter = (await session.execute(
                select(User).where(User.telegram_id == referrer_telegram_id)
            )).scalar_one_or_none()

            invited = (await session.execute(
                select(User).where(User.telegram_id == invited_telegram_id)
            )).scalar_one_or_none()

            if not inviter or not invited:
                return {"success": False, "inviter_frozen": False}

            if invited.referred_by is not None:
                print(f"[INFO] {invited_telegram_id} уже имеет реферера {invited.referred_by}")
                return {"success": False, "inviter_frozen": False}

            # Фиксируем связь. Счётчик будет обновлён в mark_webapp_opened.
            invited.referred_by     = referrer_telegram_id
            invited.referral_pending = True
            session.add(invited)

            print(f"[REFERRAL PENDING] {invited_telegram_id} → {referrer_telegram_id} (ждём открытия WebApp)")

    return {"success": True, "inviter_frozen": bool(inviter.is_frozen)}


async def mark_webapp_opened(telegram_id: int, ip_address: str) -> dict:
    """
    Вызывается при первом открытии WebApp пользователем.
    Если у пользователя есть отложенный реферал (referral_pending=True) —
    засчитывает его с полными проверками (IP-лимит, дневной лимит, заморозка).

    Возвращает dict:
      already_opened            — WebApp уже был открыт ранее
      counted                   — реферал засчитан
      inviter_frozen            — инвайтер заморожен (добавлено в frozen_referrals)
      needs_review_notification — достигнут порог авто-заморозки
      referrals_count           — текущее кол-во рефералов инвайтера
      inviter_id                — telegram_id инвайтера (для уведомлений)
      blocked_reason            — причина, если not counted: ip_limit / daily_limit / no_referral
    """
    from config import REFERRAL_REVIEW_THRESHOLD, DAILY_REFERRAL_LIMIT, IP_DAILY_LIMIT

    result = {
        "already_opened":            False,
        "counted":                   False,
        "inviter_frozen":            False,
        "needs_review_notification": False,
        "referrals_count":           0,
        "inviter_id":                None,
        "blocked_reason":            None,
    }

    async with async_session() as session:
        async with session.begin():
            user = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()

            if not user:
                return result

            if user.webapp_opened:
                result["already_opened"] = True
                return result

            # Фиксируем открытие и IP
            user.webapp_opened   = True
            user.registration_ip = ip_address
            session.add(user)

            if not user.referral_pending or not user.referred_by:
                result["blocked_reason"] = "no_referral"
                return result

            # ── IP-лимит ────────────────────────────────────────────────
            today_start = datetime.datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            ip_count = await session.scalar(
                select(func.count(User.id))
                .where(User.registration_ip == ip_address)
                .where(User.webapp_opened   == True)
                .where(User.joined_at       >= today_start)
                .where(User.telegram_id     != telegram_id)
            )
            if (ip_count or 0) >= IP_DAILY_LIMIT:
                user.referral_pending = False
                session.add(user)
                result["blocked_reason"] = "ip_limit"
                print(f"[IP LIMIT] {telegram_id} с IP {ip_address} — лимит {IP_DAILY_LIMIT} достигнут")
                return result

            # ── Дневной лимит инвайтера ──────────────────────────────────
            inviter = (await session.execute(
                select(User).where(User.telegram_id == user.referred_by)
            )).scalar_one_or_none()

            if not inviter:
                user.referral_pending = False
                session.add(user)
                return result

            today_count = await session.scalar(
                select(func.count(User.id))
                .where(User.referred_by  == inviter.telegram_id)
                .where(User.webapp_opened == True)
                .where(User.joined_at    >= today_start)
            )
            if (today_count or 0) >= DAILY_REFERRAL_LIMIT:
                user.referral_pending = False
                session.add(user)
                result["blocked_reason"] = "daily_limit"
                print(f"[DAILY LIMIT] инвайтер {inviter.telegram_id} — лимит {DAILY_REFERRAL_LIMIT}/сут")
                return result

            # ── Засчитываем реферал ──────────────────────────────────────
            user.referral_pending = False
            session.add(user)

            result["inviter_id"] = inviter.telegram_id

            if inviter.is_frozen:
                inviter.frozen_referrals = (inviter.frozen_referrals or 0) + 1
                session.add(inviter)
                result["inviter_frozen"]  = True
                result["referrals_count"] = inviter.referrals
                print(f"[REFERRAL FROZEN] {telegram_id} → {inviter.telegram_id} "
                      f"(frozen_referrals={inviter.frozen_referrals})")
            else:
                inviter.referrals += 1

                if (inviter.referrals % REFERRAL_REVIEW_THRESHOLD == 0
                        and not inviter.needs_review):
                    inviter.is_frozen    = True
                    inviter.needs_review = True
                    result["needs_review_notification"] = True
                    print(f"[AUTO-FREEZE] {inviter.telegram_id} — {inviter.referrals} рефералов")

                session.add(inviter)
                result["counted"]         = True
                result["referrals_count"] = inviter.referrals
                print(f"[REFERRAL OK] {telegram_id} → {inviter.telegram_id} "
                      f"(итого: {inviter.referrals})")

    return result


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


async def admin_add_referral(referrer_telegram_id: int, invited_telegram_id: int) -> dict:
    """
    Ручное добавление реферала администратором.
    Обходит проверку заморозки, но соблюдает остальные правила
    (нет самореферала, нет дублей).
    Возвращает {"ok": bool, "reason": str, "referrals_count": int}
    """
    from config import REFERRAL_REVIEW_THRESHOLD

    if referrer_telegram_id == invited_telegram_id:
        return {"ok": False, "reason": "self_referral", "referrals_count": 0}

    async with async_session() as session:
        async with session.begin():
            inviter = (await session.execute(
                select(User).where(User.telegram_id == referrer_telegram_id)
            )).scalar_one_or_none()

            invited = (await session.execute(
                select(User).where(User.telegram_id == invited_telegram_id)
            )).scalar_one_or_none()

            if not inviter:
                return {"ok": False, "reason": "inviter_not_found", "referrals_count": 0}
            if not invited:
                return {"ok": False, "reason": "invited_not_found", "referrals_count": 0}

            if invited.referred_by is not None:
                return {"ok": False, "reason": "already_has_referrer",
                        "referrals_count": inviter.referrals}

            invited.referred_by = referrer_telegram_id
            session.add(invited)

            inviter.referrals += 1
            session.add(inviter)

            print(f"[ADMIN ADD REFERRAL] {invited_telegram_id} → {referrer_telegram_id} "
                  f"(итого: {inviter.referrals})")

            return {"ok": True, "reason": "ok", "referrals_count": inviter.referrals}


async def admin_increment_referrals(referrer_telegram_id: int, count: int = 1) -> dict:
    """
    Добавить N рефералов к счётчику без реальных пользователей в БД.
    Используется администратором для ручной корректировки.
    Возвращает {"ok": bool, "reason": str, "referrals_count": int}
    """
    if count < 1 or count > 10000:
        return {"ok": False, "reason": "invalid_count", "referrals_count": 0}

    async with async_session() as session:
        async with session.begin():
            inviter = (await session.execute(
                select(User).where(User.telegram_id == referrer_telegram_id)
            )).scalar_one_or_none()

            if not inviter:
                return {"ok": False, "reason": "inviter_not_found", "referrals_count": 0}

            inviter.referrals += count
            session.add(inviter)

            print(f"[ADMIN INCREMENT] {referrer_telegram_id} +{count} → итого {inviter.referrals}")
            return {"ok": True, "reason": "ok", "referrals_count": inviter.referrals}


async def freeze_subtree(root_telegram_id: int, freeze: bool = True) -> dict:
    """
    Заморозить / разморозить всех рефералов пользователя рекурсивно
    (сам пользователь не затрагивается).
    Возвращает {"ok": bool, "affected": int, "ids": list[int]}
    """
    sql_find = text("""
        WITH RECURSIVE subtree AS (
            SELECT telegram_id
            FROM users
            WHERE referred_by = :root_id

            UNION ALL

            SELECT u.telegram_id
            FROM users u
            INNER JOIN subtree s ON u.referred_by = s.telegram_id
        )
        SELECT telegram_id FROM subtree
    """)

    sql_update = text("""
        WITH RECURSIVE subtree AS (
            SELECT telegram_id
            FROM users
            WHERE referred_by = :root_id

            UNION ALL

            SELECT u.telegram_id
            FROM users u
            INNER JOIN subtree s ON u.referred_by = s.telegram_id
        )
        UPDATE users
        SET is_frozen = :freeze
        WHERE telegram_id IN (SELECT telegram_id FROM subtree)
        RETURNING telegram_id
    """)

    async with engine.begin() as conn:
        result = await conn.execute(sql_update, {"root_id": root_telegram_id, "freeze": freeze})
        affected_ids = [row[0] for row in result.fetchall()]

    action = "заморожено" if freeze else "разморожено"
    print(f"[FREEZE SUBTREE] root={root_telegram_id} → {action} {len(affected_ids)} пользователей")
    return {"ok": True, "affected": len(affected_ids), "ids": affected_ids}


async def get_all_users() -> list[User]:
    async with async_session() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


# ─── Новые функции для реферальной админки ────────────────────────────────────

async def freeze_user(telegram_id: int, freeze: bool) -> bool:
    """Заморозить / разморозить пользователя. Возвращает True если юзер найден."""
    async with async_session() as session:
        async with session.begin():
            user = await get_user(telegram_id, session)
            if not user:
                return False
            user.is_frozen = freeze
            session.add(user)
            return True


async def approve_user(telegram_id: int) -> dict:
    """
    Одобрить после ручной проверки: снять заморозку и восстановить
    рефералов, пришедших во время заморозки (из поля frozen_referrals).

    Возвращает: ok, referrals_before, referrals_after, restored
    """
    async with async_session() as session:
        async with session.begin():
            user = await get_user(telegram_id, session)
            if not user:
                return {"ok": False, "referrals_before": 0, "referrals_after": 0, "restored": 0}

            referrals_before  = user.referrals
            frozen_count      = user.frozen_referrals or 0

            user.referrals       += frozen_count   # переносим замороженные в основной счётчик
            user.frozen_referrals = 0
            user.needs_review     = False
            user.is_frozen        = False
            session.add(user)

            print(f"[APPROVE] {telegram_id}: referrals {referrals_before} → {user.referrals} "
                  f"(frozen_referrals восстановлено: +{frozen_count})")

            return {
                "ok":               True,
                "referrals_before": referrals_before,
                "referrals_after":  user.referrals,
                "restored":         frozen_count,
            }


async def dismiss_review(telegram_id: int) -> bool:
    """Убрать из очереди проверки, но оставить замороженным."""
    async with async_session() as session:
        async with session.begin():
            user = await get_user(telegram_id, session)
            if not user:
                return False
            user.needs_review = False
            session.add(user)
            return True


async def get_users_for_review() -> list[User]:
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .where(User.needs_review == True)
            .order_by(User.referrals.desc())
        )
        return result.scalars().all()


async def get_all_referrers_paginated(
    page: int = 1,
    limit: int = 50,
    sort_by: str = "referrals",
    sort_dir: str = "desc",
) -> dict:
    """Пагинированный список юзеров у которых есть рефералы."""
    async with async_session() as session:
        col = getattr(User, sort_by, User.referrals)
        order = col.desc() if sort_dir == "desc" else col.asc()

        total = await session.scalar(
            select(func.count(User.id)).where(User.referrals > 0)
        )
        result = await session.execute(
            select(User)
            .where(User.referrals > 0)
            .order_by(order)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        users = result.scalars().all()
        return {
            "users": users,
            "total": total or 0,
            "page": page,
            "pages": max(1, ((total or 0) + limit - 1) // limit),
        }


async def get_referral_tree(root_telegram_id: int, max_depth: int = 3) -> dict:
    """
    Строит дерево рефералов через рекурсивный CTE PostgreSQL.
    Возвращает словарь для D3.js hierarchy.
    Дочерние узлы обрезаются до 100 на уровень (добавляется truncated_count).
    """
    max_depth = min(max_depth, 4)

    sql = text("""
        WITH RECURSIVE tree AS (
            SELECT telegram_id, referred_by, referrals,
                   COALESCE(is_frozen, false) AS is_frozen,
                   COALESCE(needs_review, false) AS needs_review,
                   0 AS depth
            FROM users
            WHERE telegram_id = :root_id

            UNION ALL

            SELECT u.telegram_id, u.referred_by, u.referrals,
                   COALESCE(u.is_frozen, false),
                   COALESCE(u.needs_review, false),
                   t.depth + 1
            FROM users u
            INNER JOIN tree t ON u.referred_by = t.telegram_id
            WHERE t.depth < :max_depth
        )
        SELECT * FROM tree ORDER BY depth ASC, referrals DESC
    """)

    async with async_session() as session:
        result = await session.execute(sql, {"root_id": root_telegram_id, "max_depth": max_depth})
        rows = result.mappings().all()

    if not rows:
        return {"id": root_telegram_id, "referrals": 0, "frozen": False, "needs_review": False, "children": []}

    MAX_CHILDREN = 100

    nodes: dict[int, dict] = {}
    for row in rows:
        nodes[row["telegram_id"]] = {
            "id": row["telegram_id"],
            "referrals": row["referrals"],
            "frozen": bool(row["is_frozen"]),
            "needs_review": bool(row["needs_review"]),
            "depth": row["depth"],
            "children": [],
        }

    root = None
    for row in rows:
        tid = row["telegram_id"]
        parent_id = row["referred_by"]
        node = nodes[tid]

        if tid == root_telegram_id:
            root = node
        elif parent_id and parent_id in nodes:
            parent = nodes[parent_id]
            if len(parent["children"]) < MAX_CHILDREN:
                parent["children"].append(node)
            else:
                # Отметить что есть обрезка
                parent["truncated_count"] = parent.get("truncated_count", 0) + 1

    return root or {"id": root_telegram_id, "referrals": 0, "frozen": False, "needs_review": False, "children": []}


async def get_referrals_per_day(days: int = 30) -> list[dict]:
    """
    Возвращает список {"date": "2024-01-15", "count": 42} за последние N дней.
    Учитывает только юзеров с joined_at (новые после миграции) и с referred_by IS NOT NULL.
    """
    sql = text("""
        SELECT DATE(joined_at) AS date, COUNT(*) AS count
        FROM users
        WHERE joined_at IS NOT NULL
          AND joined_at >= NOW() - INTERVAL '1 day' * :days
          AND referred_by IS NOT NULL
        GROUP BY DATE(joined_at)
        ORDER BY date ASC
    """)
    async with async_session() as session:
        result = await session.execute(sql, {"days": days})
        return [{"date": str(row["date"]), "count": row["count"]}
                for row in result.mappings().all()]
