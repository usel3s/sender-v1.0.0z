import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Account, UserSettings


def parse_id_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [int(x) for x in data] if isinstance(data, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


async def get_user_accounts(session: AsyncSession, user_id: int) -> list[Account]:
    result = await session.execute(
        select(Account)
        .where(Account.user_id == user_id, Account.status == "active")
        .order_by(Account.created_at)
    )
    return list(result.scalars().all())


async def get_selected_account_ids(session: AsyncSession, user_id: int) -> list[int]:
    accounts = await get_user_accounts(session, user_id)
    if not accounts:
        return []

    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    ).scalar_one_or_none()
    if settings is None:
        return [account.id for account in accounts]

    valid_ids = {account.id for account in accounts}
    selected = [account_id for account_id in parse_id_list(settings.selected_account_ids_json) if account_id in valid_ids]
    return selected or [account.id for account in accounts]


async def set_selected_account_ids(session: AsyncSession, user_id: int, account_ids: list[int]) -> None:
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    ).scalar_one_or_none()
    if settings is None:
        return
    settings.selected_account_ids_json = json.dumps(account_ids)


async def ensure_account_selected(session: AsyncSession, user_id: int, account_id: int) -> None:
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    ).scalar_one_or_none()
    if settings is None:
        return
    selected = parse_id_list(settings.selected_account_ids_json)
    if account_id not in selected:
        selected.append(account_id)
        settings.selected_account_ids_json = json.dumps(selected)


def account_label(account: Account) -> str:
    return account.name or account.phone_number or f"Аккаунт #{account.id}"
