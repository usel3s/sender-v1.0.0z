import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select

from bot.keyboards.main import MENU_BUTTONS, broadcast_keyboard
from bot.services import chat_ui
from bot.services.dm_sender import broadcast_manager
from bot.states import BroadcastStates
from bot.utils import emojis as E
from bot.utils.texts import broadcast_status_label
from database.database import async_session
from database.models import Account, BroadcastJob, RecipientList, User

router = Router()


@router.message(F.text == "Рассылка")
async def menu_broadcast(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    running = broadcast_manager.is_running(db_user.tg_id)
    if not running:
        await state.set_state(BroadcastStates.waiting_message)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.SEND_UP, '⬆')} <b>Рассылка в ЛС</b>\n\n"
        "Отправьте текст сообщения для рассылки, затем нажмите «Начать рассылку».",
        reply_markup=broadcast_keyboard(running=running),
    )


@router.message(BroadcastStates.waiting_message, F.text, ~F.text.in_(MENU_BUTTONS))
async def broadcast_message_received(message: Message, state: FSMContext, db_user: User) -> None:
    await state.update_data(message_html=message.html_text or message.text)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.EYE, '👁')} <b>Предпросмотр сообщения:</b>\n\n{message.html_text or message.text}\n\n"
        "Нажмите «Начать рассылку» для запуска.",
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
        account = (
            await session.execute(select(Account).where(Account.user_id == db_user.id))
        ).scalar_one_or_none()
        if not account:
            await callback.answer("Сначала подключите аккаунт", show_alert=True)
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
                f"{E.e(E.WRITE, '✍')} Отправьте текст сообщения для рассылки:",
                reply_markup=broadcast_keyboard(),
            )
            await state.set_state(BroadcastStates.waiting_message)
            await callback.answer()
            return

        recipients = json.loads(recipient_list.recipients_json)
        job = BroadcastJob(
            user_id=db_user.id,
            account_id=account.id,
            message_html=message_html,
            status="pending",
            total=len(recipients),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    ui_message_id = await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.LOADING, '🔄')} Рассылка запущена... 0/{len(recipients)}",
        reply_markup=broadcast_keyboard(running=True),
    )

    async def progress_callback(sent, failed, total, status):
        if not callback.message or not ui_message_id:
            return
        status_text = broadcast_status_label(status)
        try:
            await callback.bot.edit_message_text(
                f"{E.e(E.SEND_UP, '⬆')} Рассылка {status_text}\n\n"
                f"Отправлено: <b>{sent}</b>\n"
                f"Ошибок: <b>{failed}</b>\n"
                f"Всего: <b>{total}</b>",
                chat_id=callback.message.chat.id,
                message_id=ui_message_id,
                reply_markup=broadcast_keyboard(running=status == "running"),
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
        )
    except RuntimeError as e:
        await callback.answer(str(e), show_alert=True)
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
