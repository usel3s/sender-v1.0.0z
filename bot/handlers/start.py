from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

import config
from bot.keyboards.main import no_access_keyboard
from bot.services import chat_ui
from bot.utils import emojis as E
from database.database import async_session
from database.models import BotSettings, User

router = Router()


async def get_start_text() -> str:
    async with async_session() as session:
        settings = await session.get(BotSettings, 1)
        if settings and settings.start_message_html:
            return settings.start_message_html
    return config.DEFAULT_START_MESSAGE


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    if not db_user.has_access and not db_user.is_admin:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.LOCK_CLOSED, '🔒')} <b>Нет доступа</b>\n\nОбратитесь к администратору.",
            reply_markup=no_access_keyboard(),
            delete_user=True,
            keep_menu=False,
        )
        return

    text = await get_start_text()
    await chat_ui.show_from_message(message, db_user.id, text, with_main_menu=True, delete_user=True)


@router.callback_query(F.data == "request_access")
async def request_access(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer("Запрос отправлен администратору", show_alert=True)
    for admin_id in config.ADMIN_IDS:
        try:
            username = f"@{db_user.username}" if db_user.username else str(db_user.tg_id)
            await callback.bot.send_message(
                admin_id,
                f"{E.e(E.BELL, '🔔')} Запрос доступа от {username} (<code>{db_user.tg_id}</code>)",
            )
        except Exception:
            pass


@router.callback_query(F.data == "menu_back")
async def menu_back(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not db_user.has_access and not db_user.is_admin:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    text = await get_start_text()
    await chat_ui.show_from_callback(callback, db_user.id, text)
    await callback.answer()


@router.message(F.text == "Профиль")
async def menu_profile(message: Message, db_user: User) -> None:
    from bot.services.dm_sender import broadcast_manager
    from database.models import Account, UserSettings

    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == db_user.id))
        ).scalar_one_or_none()
        accounts = (
            await session.execute(select(Account).where(Account.user_id == db_user.id))
        ).scalars().all()

    running = broadcast_manager.is_running(db_user.tg_id)
    account_text = accounts[0].name if accounts else "Не подключён"
    delay = settings.message_delay_sec if settings else 60
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.PROFILE, '👤')} <b>Профиль</b>\n\n"
        f"Аккаунт: <b>{account_text}</b>\n"
        f"КД: <b>{delay} сек</b>\n"
        f"Рассылка: <b>{'активна' if running else 'остановлена'}</b>",
    )
