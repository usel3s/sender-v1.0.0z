from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import settings_keyboard
from bot.services import chat_ui
from bot.states import SettingsStates
from bot.utils import emojis as E
from database.database import async_session
from database.models import User, UserSettings

router = Router()


async def get_user_settings(db_user: User) -> UserSettings:
    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == db_user.id))
        ).scalar_one_or_none()
        if settings is None:
            settings = UserSettings(user_id=db_user.id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        return settings


def _settings_text(settings: UserSettings) -> str:
    return (
        f"{E.e(E.SETTINGS, '⚙️')} <b>Настройки КД</b>\n\n"
        f"КД между сообщениями: <b>{settings.message_delay_sec} сек</b>\n"
        f"Лимит в час: <b>{settings.hourly_limit}</b>\n"
        f"Лимит в день: <b>{settings.daily_limit}</b>\n\n"
        "Рекомендуется КД 60–180 сек для снижения риска блокировки."
    )


@router.message(F.text == "Настройки")
async def menu_settings(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    settings = await get_user_settings(db_user)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        _settings_text(settings),
        reply_markup=settings_keyboard(),
    )


@router.callback_query(F.data == "settings_delay")
async def settings_delay(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CLOCK, '⏰')} Введите КД между сообщениями в секундах (мин. 30):",
        reply_markup=settings_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_delay)
    await callback.answer()


@router.message(SettingsStates.waiting_delay)
async def settings_delay_value(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        value = int(message.text.strip())
        if value < 30:
            raise ValueError
    except ValueError:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Введите число от 30 и выше.",
            reply_markup=settings_keyboard(),
        )
        return

    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == db_user.id))
        ).scalar_one()
        settings.message_delay_sec = value
        await session.commit()
        await session.refresh(settings)

    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} КД установлен: <b>{value} сек</b>\n\n{_settings_text(settings)}",
        reply_markup=settings_keyboard(),
    )


@router.callback_query(F.data == "settings_hourly")
async def settings_hourly(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CHART_GROWTH, '📊')} Введите лимит сообщений в час:",
        reply_markup=settings_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_hourly)
    await callback.answer()


@router.message(SettingsStates.waiting_hourly)
async def settings_hourly_value(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        value = int(message.text.strip())
        if value < 1:
            raise ValueError
    except ValueError:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Введите положительное число.",
            reply_markup=settings_keyboard(),
        )
        return

    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == db_user.id))
        ).scalar_one()
        settings.hourly_limit = value
        await session.commit()
        await session.refresh(settings)

    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Лимит в час: <b>{value}</b>\n\n{_settings_text(settings)}",
        reply_markup=settings_keyboard(),
    )


@router.callback_query(F.data == "settings_daily")
async def settings_daily(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CALENDAR, '📅')} Введите лимит сообщений в день:",
        reply_markup=settings_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_daily)
    await callback.answer()


@router.message(SettingsStates.waiting_daily)
async def settings_daily_value(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        value = int(message.text.strip())
        if value < 1:
            raise ValueError
    except ValueError:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Введите положительное число.",
            reply_markup=settings_keyboard(),
        )
        return

    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == db_user.id))
        ).scalar_one()
        settings.daily_limit = value
        await session.commit()
        await session.refresh(settings)

    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Лимит в день: <b>{value}</b>\n\n{_settings_text(settings)}",
        reply_markup=settings_keyboard(),
    )
