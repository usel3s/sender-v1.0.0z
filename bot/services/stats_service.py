from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database.models import Account, BroadcastJob, User


async def get_bot_stats(session: AsyncSession, bot, active_jobs: int) -> dict:
    total_users = await session.scalar(select(func.count(User.id))) or 0
    active_access = await session.scalar(select(func.count(User.id)).where(User.has_access.is_(True))) or 0
    accounts_count = await session.scalar(select(func.count(Account.id))) or 0

    channel_count = None
    if config.PRIVATE_CHANNEL_ID:
        try:
            channel_count = await bot.get_chat_member_count(config.PRIVATE_CHANNEL_ID)
        except Exception:
            channel_count = None

    return {
        "total_users": total_users,
        "active_access": active_access,
        "channel_count": channel_count,
        "active_jobs": active_jobs,
        "accounts_count": accounts_count,
    }
