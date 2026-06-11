from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select

import config
from bot.keyboards.main import admin_back_keyboard, admin_menu_keyboard, back_button, confirm_keyboard
from bot.services import chat_ui
from bot.services.stats_service import get_bot_stats
from bot.utils.texts import admin_toggle_label, access_toggle_label, yes_no
from bot.states import AdminStates
from bot.utils import emojis as E
from database.database import async_session
from database.models import BotSettings, User

router = Router()


def is_admin(user: User) -> bool:
    return user.is_admin or user.tg_id in config.ADMIN_IDS


def _admin_menu_text() -> str:
    return f"{E.e(E.SETTINGS, '⚙️')} <b>Админ-панель</b>\n\nВыберите раздел:"


@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: User) -> None:
    if not is_admin(db_user):
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} У вас нет доступа к админ-панели.",
            delete_user=False,
        )
        return
    await chat_ui.show_from_message(
        message,
        db_user.id,
        _admin_menu_text(),
        reply_markup=admin_menu_keyboard(),
        delete_user=True,
    )


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await chat_ui.show_from_callback(callback, db_user.id, _admin_menu_text(), reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    from bot.services.dm_sender import broadcast_manager

    async with async_session() as session:
        stats = await get_bot_stats(session, callback.bot, broadcast_manager.active_count())

    channel_line = (
        f"В приватном канале: <b>{stats['channel_count']}</b>"
        if stats["channel_count"] is not None
        else "В приватном канале: <b>недоступно</b>"
    )

    text = (
        f"{E.e(E.CHART_STATS, '📊')} <b>Статистика</b>\n\n"
        f"Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"С активным доступом: <b>{stats['active_access']}</b>\n"
        f"{channel_line}\n"
        f"Активных рассылок: <b>{stats['active_jobs']}</b>\n"
        f"Подключённых аккаунтов: <b>{stats['accounts_count']}</b>"
    )
    await chat_ui.show_from_callback(callback, db_user.id, text, reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_start_msg")
async def admin_start_msg(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.PENCIL, '🖋')} <b>Стартовое сообщение</b>\n\n"
        "Отправьте новый текст для /start. Поддерживается разметка HTML и премиум-эмодзи "
        '<code>&lt;tg-emoji emoji-id="..."&gt;</code>.',
        reply_markup=admin_back_keyboard(),
    )
    await state.set_state(AdminStates.waiting_start_message)
    await callback.answer()


@router.message(AdminStates.waiting_start_message)
async def admin_start_message_received(message: Message, state: FSMContext, db_user: User) -> None:
    if not is_admin(db_user):
        return
    await state.update_data(start_message_html=message.html_text or message.text)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.EYE, '👁')} <b>Предпросмотр стартового сообщения:</b>\n\n{message.html_text or message.text}",
        reply_markup=confirm_keyboard("admin_start_confirm", "admin_start_cancel"),
    )
    await state.set_state(AdminStates.waiting_start_preview_confirm)


@router.callback_query(F.data == "admin_start_confirm")
async def admin_start_confirm(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    html = data.get("start_message_html", "")
    async with async_session() as session:
        settings = await session.get(BotSettings, 1)
        settings.start_message_html = html
        await session.commit()
    await state.clear()
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Стартовое сообщение обновлено.",
        reply_markup=admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_start_cancel")
async def admin_start_cancel(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await admin_back(callback, db_user)


@router.callback_query(F.data == "admin_access")
async def admin_access(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with async_session() as session:
        users = (
            await session.execute(select(User).order_by(desc(User.registered_at)).limit(10))
        ).scalars().all()

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for u in users:
        label = f"@{u.username}" if u.username else str(u.tg_id)
        access_icon = E.CHECK if u.has_access else E.CROSS
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin_user_{u.id}",
                icon_custom_emoji_id=access_icon,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Поиск пользователя",
            callback_data="admin_search_user",
            icon_custom_emoji_id=E.EYE,
        )
    ])
    rows.append([back_button()])

    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.LOCK_OPEN, '🔓')} <b>Выдача доступа</b>\n\nПоследние пользователи:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


async def _render_user_panel(callback: CallbackQuery, user: User, db_user: User) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    label = f"@{user.username}" if user.username else str(user.tg_id)
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.PROFILE, '👤')} <b>{label}</b>\n\n"
        f"Telegram ID: <code>{user.tg_id}</code>\n"
        f"Доступ к боту: <b>{yes_no(user.has_access)}</b>\n"
        f"Права админа: <b>{yes_no(user.is_admin)}</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=access_toggle_label(user.has_access),
                        callback_data=f"admin_toggle_access_{user.id}",
                        icon_custom_emoji_id=E.LOCK_OPEN if not user.has_access else E.LOCK_CLOSED,
                    ),
                    InlineKeyboardButton(
                        text=admin_toggle_label(user.is_admin),
                        callback_data=f"admin_toggle_admin_{user.id}",
                        icon_custom_emoji_id=E.SETTINGS,
                    ),
                ],
                [back_button("admin_access")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("admin_user_"))
async def admin_user_detail(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
    await _render_user_panel(callback, user, db_user)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_toggle_access_"))
async def admin_toggle_access(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        user = await session.get(User, user_id)
        user.has_access = not user.has_access
        new_access = user.has_access
        await session.commit()
        await session.refresh(user)
    await _render_user_panel(callback, user, db_user)
    await callback.answer("Доступ выдан" if new_access else "Доступ отозван")


@router.callback_query(F.data.startswith("admin_toggle_admin_"))
async def admin_toggle_admin(callback: CallbackQuery, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        user = await session.get(User, user_id)
        user.is_admin = not user.is_admin
        if user.is_admin:
            user.has_access = True
        new_admin = user.is_admin
        await session.commit()
        await session.refresh(user)
    await _render_user_panel(callback, user, db_user)
    await callback.answer("Пользователь назначен админом" if new_admin else "Права админа сняты")


@router.callback_query(F.data == "admin_search_user")
async def admin_search_user(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not is_admin(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.EYE, '👁')} Отправьте @username или числовой Telegram ID:",
        reply_markup=admin_back_keyboard(),
    )
    await state.set_state(AdminStates.waiting_access_search)
    await callback.answer()


@router.message(AdminStates.waiting_access_search)
async def admin_search_user_message(message: Message, state: FSMContext, db_user: User) -> None:
    if not is_admin(db_user):
        return
    query = (message.text or "").strip().lstrip("@")
    async with async_session() as session:
        if query.isdigit():
            user = (await session.execute(select(User).where(User.tg_id == int(query)))).scalar_one_or_none()
        else:
            user = (await session.execute(select(User).where(User.username == query))).scalar_one_or_none()
        if not user:
            await chat_ui.show_from_message(
                message,
                db_user.id,
                f"{E.e(E.CROSS, '❌')} Пользователь не найден.",
                reply_markup=admin_back_keyboard(),
            )
            return

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    label = f"@{user.username}" if user.username else str(user.tg_id)
    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.PROFILE, '👤')} Найден: <b>{label}</b> (<code>{user.tg_id}</code>)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=access_toggle_label(user.has_access),
                        callback_data=f"admin_toggle_access_{user.id}",
                        icon_custom_emoji_id=E.LOCK_OPEN if not user.has_access else E.LOCK_CLOSED,
                    )
                ],
                [back_button("admin_access")],
            ]
        ),
    )
