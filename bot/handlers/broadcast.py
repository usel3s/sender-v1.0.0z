import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select

from bot.keyboards.main import MENU_BUTTONS, broadcast_accounts_keyboard, broadcast_keyboard
from bot.services import chat_ui
from bot.services.account_service import (
    account_label,
    get_selected_account_ids,
    get_user_accounts,
    set_selected_account_ids,
)
from bot.services.dm_sender import broadcast_manager
from bot.states import BroadcastStates
from bot.utils import emojis as E
from bot.utils.texts import broadcast_status_label
from database.database import async_session
from database.models import BroadcastJob, RecipientList, User

router = Router()


async def _broadcast_text(db_user: User, *, message_html: str | None = None, preview: bool = False) -> str:
    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        selected_ids = await get_selected_account_ids(session, db_user.id)

    selected_names = [
        account_label(account)
        for account in accounts
        if account.id in selected_ids
    ]
    accounts_line = ", ".join(selected_names) if selected_names else "не выбраны"

    if preview and message_html:
        return (
            f"{E.e(E.EYE, '👁')} <b>Предпросмотр сообщения:</b>\n\n{message_html}\n\n"
            f"Аккаунты: <b>{accounts_line}</b>\n\n"
            "Нажмите «Начать рассылку» для запуска."
        )

    return (
        f"{E.e(E.SEND_UP, '⬆')} <b>Рассылка в ЛС</b>\n\n"
        f"Аккаунты: <b>{accounts_line}</b>\n\n"
        "Отправьте текст сообщения для рассылки, затем нажмите «Начать рассылку»."
    )


async def _accounts_picker_text(accounts, selected_ids: set[int]) -> str:
    lines = [f"{E.e(E.PROFILE, '👤')} <b>Аккаунты для рассылки</b>\n"]
    if not accounts:
        lines.append("Сначала подключите аккаунты в разделе «Аккаунт».")
    else:
        lines.append("Нажмите на аккаунт, чтобы включить или выключить его.\n")
        for account in accounts:
            mark = "✅" if account.id in selected_ids else "⬜"
            lines.append(f"{mark} {account_label(account)}")
        lines.append(f"\nВыбрано: <b>{len(selected_ids)}</b> из <b>{len(accounts)}</b>")
    return "\n".join(lines)


@router.message(F.text == "Рассылка")
async def menu_broadcast(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    running = broadcast_manager.is_running(db_user.tg_id)
    if not running:
        await state.set_state(BroadcastStates.waiting_message)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        await _broadcast_text(db_user),
        reply_markup=broadcast_keyboard(running=running),
    )


@router.callback_query(F.data == "broadcast_back")
async def broadcast_back(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    running = broadcast_manager.is_running(db_user.tg_id)
    data = await state.get_data()
    message_html = data.get("message_html")
    if message_html:
        text = await _broadcast_text(db_user, message_html=message_html, preview=True)
        await state.set_state(BroadcastStates.waiting_confirm)
    else:
        text = await _broadcast_text(db_user)
        if not running:
            await state.set_state(BroadcastStates.waiting_message)
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        text,
        reply_markup=broadcast_keyboard(running=running),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_accounts")
async def broadcast_accounts(callback: CallbackQuery, db_user: User) -> None:
    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        selected_ids = set(await get_selected_account_ids(session, db_user.id))

    if not accounts:
        await callback.answer("Сначала подключите аккаунт", show_alert=True)
        return

    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        await _accounts_picker_text(accounts, selected_ids),
        reply_markup=broadcast_accounts_keyboard(accounts, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast_toggle_"))
async def broadcast_toggle_account(callback: CallbackQuery, db_user: User) -> None:
    account_id = int(callback.data.removeprefix("broadcast_toggle_"))
    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        valid_ids = {account.id for account in accounts}
        if account_id not in valid_ids:
            await callback.answer("Аккаунт не найден", show_alert=True)
            return

        selected_ids = set(await get_selected_account_ids(session, db_user.id))
        if account_id in selected_ids:
            selected_ids.remove(account_id)
        else:
            selected_ids.add(account_id)
        await set_selected_account_ids(session, db_user.id, sorted(selected_ids))
        await session.commit()

    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        await _accounts_picker_text(accounts, selected_ids),
        reply_markup=broadcast_accounts_keyboard(accounts, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_select_all")
async def broadcast_select_all(callback: CallbackQuery, db_user: User) -> None:
    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        selected_ids = {account.id for account in accounts}
        await set_selected_account_ids(session, db_user.id, sorted(selected_ids))
        await session.commit()

    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        await _accounts_picker_text(accounts, selected_ids),
        reply_markup=broadcast_accounts_keyboard(accounts, selected_ids),
    )
    await callback.answer("Все аккаунты выбраны")


@router.callback_query(F.data == "broadcast_select_none")
async def broadcast_select_none(callback: CallbackQuery, db_user: User) -> None:
    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        selected_ids: set[int] = set()
        await set_selected_account_ids(session, db_user.id, [])
        await session.commit()

    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        await _accounts_picker_text(accounts, selected_ids),
        reply_markup=broadcast_accounts_keyboard(accounts, selected_ids),
    )
    await callback.answer("Выбор снят")


@router.message(BroadcastStates.waiting_message, F.text, ~F.text.in_(MENU_BUTTONS))
async def broadcast_message_received(message: Message, state: FSMContext, db_user: User) -> None:
    message_html = message.html_text or message.text
    await state.update_data(message_html=message_html)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        await _broadcast_text(db_user, message_html=message_html, preview=True),
        reply_markup=broadcast_keyboard(),
    )
    await state.set_state(BroadcastStates.waiting_confirm)


@router.callback_query(F.data == "broadcast_start")
async def broadcast_start(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if broadcast_manager.is_running(db_user.tg_id):
        await callback.answer("Рассылка уже запущена", show_alert=True)
        return

    data = await state.get_data()
    message_html = data.get("message_html")

    async with async_session() as session:
        accounts = await get_user_accounts(session, db_user.id)
        if not accounts:
            await callback.answer("Сначала подключите аккаунт", show_alert=True)
            return

        selected_ids = await get_selected_account_ids(session, db_user.id)
        if not selected_ids:
            await callback.answer("Выберите хотя бы один аккаунт", show_alert=True)
            return

        recipient_list = (
            await session.execute(
                select(RecipientList)
                .where(RecipientList.user_id == db_user.id)
                .order_by(desc(RecipientList.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not recipient_list:
            await callback.answer("Загрузите список получателей", show_alert=True)
            return

        if not message_html:
            await chat_ui.show_from_callback(
                callback,
                db_user.id,
                await _broadcast_text(db_user),
                reply_markup=broadcast_keyboard(),
            )
            await state.set_state(BroadcastStates.waiting_message)
            await callback.answer()
            return

        recipients = json.loads(recipient_list.recipients_json)
        job = BroadcastJob(
            user_id=db_user.id,
            account_id=selected_ids[0],
            account_ids_json=json.dumps(selected_ids),
            message_html=message_html,
            status="pending",
            total=len(recipients),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    accounts_count = len(selected_ids)
    ui_message_id = await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.LOADING, '🔄')} Рассылка запущена ({accounts_count} акк.)... 0/{len(recipients)}",
        reply_markup=broadcast_keyboard(running=True, show_accounts=False),
    )

    async def progress_callback(sent, failed, total, status):
        if not callback.message or not ui_message_id:
            return
        status_text = broadcast_status_label(status)
        try:
            await callback.bot.edit_message_text(
                f"{E.e(E.SEND_UP, '⬆')} Рассылка {status_text}\n\n"
                f"Аккаунтов: <b>{accounts_count}</b>\n"
                f"Отправлено: <b>{sent}</b>\n"
                f"Ошибок: <b>{failed}</b>\n"
                f"Всего: <b>{total}</b>",
                chat_id=callback.message.chat.id,
                message_id=ui_message_id,
                reply_markup=broadcast_keyboard(running=status == "running", show_accounts=False),
            )
        except Exception:
            pass

    try:
        await broadcast_manager.start(
            db_user.tg_id,
            job_id,
            recipients,
            message_html,
            progress_callback,
            selected_ids,
        )
    except RuntimeError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await callback.answer("Рассылка запущена")


@router.callback_query(F.data == "broadcast_stop")
async def broadcast_stop(callback: CallbackQuery, db_user: User) -> None:
    await broadcast_manager.stop(db_user.tg_id)
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CROSS, '❌')} Рассылка останавливается...",
        reply_markup=broadcast_keyboard(running=False),
    )
    await callback.answer()
