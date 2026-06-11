from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import config
from database.models import Base, BotSettings, User, UserSettings

engine = create_async_engine(config.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in config.DATABASE_URL:
            try:
                await conn.execute(text("ALTER TABLE user_settings ADD COLUMN ui_message_id INTEGER"))
            except Exception:
                pass

    async with async_session() as session:
        settings = await session.get(BotSettings, 1)
        if settings is None:
            session.add(BotSettings(id=1, start_message_html=config.DEFAULT_START_MESSAGE))
            await session.commit()

        for admin_id in config.ADMIN_IDS:
            result = await session.execute(select(User).where(User.tg_id == admin_id))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(tg_id=admin_id, has_access=True, is_admin=True)
                session.add(user)
                await session.flush()
                session.add(UserSettings(user_id=user.id))
            else:
                user.has_access = True
                user.is_admin = True
        await session.commit()


async def get_or_create_user(session: AsyncSession, tg_id: int, username: str | None) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id, username=username, has_access=tg_id in config.ADMIN_IDS, is_admin=tg_id in config.ADMIN_IDS)
        session.add(user)
        await session.flush()
        session.add(UserSettings(user_id=user.id))
        await session.commit()
        await session.refresh(user)
    else:
        if username and user.username != username:
            user.username = username
            await session.commit()
        settings_exists = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
        ).scalar_one_or_none()
        if settings_exists is None:
            session.add(UserSettings(user_id=user.id))
            await session.commit()
    return user
