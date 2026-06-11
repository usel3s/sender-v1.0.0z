import asyncio

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from database.database import async_session
from database.models import UserSettings

# Невидимый символ для тихого обновления Reply-клавиатуры.
_KEYBOARD_REFRESH_TEXT = "\u2060"

_user_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


async def _delete_message(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _ensure_user_settings(session, user_id: int) -> UserSettings:
    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    ).scalar_one_or_none()
    if settings is None:
        settings = UserSettings(user_id=user_id)
        session.add(settings)
        await session.flush()
    return settings


async def _get_ui_message_id(user_id: int) -> int | None:
    async with async_session() as session:
        settings = (
            await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        ).scalar_one_or_none()
        return settings.ui_message_id if settings else None


async def _set_ui_message_id(user_id: int, message_id: int | None) -> None:
    async with async_session() as session:
        settings = await _ensure_user_settings(session, user_id)
        settings.ui_message_id = message_id
        await session.commit()


async def _ensure_reply_keyboard(bot, chat_id: int) -> None:
    """Обновить Reply-клавиатуру без лишнего сообщения в чате."""
    try:
        msg = await bot.send_message(
            chat_id,
            _KEYBOARD_REFRESH_TEXT,
            reply_markup=main_menu_keyboard(),
            disable_notification=True,
        )
        await _delete_message(bot, chat_id, msg.message_id)
    except Exception:
        pass


async def delete_user_message(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception:
        pass


def _inline_markup(reply_markup) -> InlineKeyboardMarkup | None:
    if isinstance(reply_markup, InlineKeyboardMarkup):
        return reply_markup
    return None


async def _apply_inline_markup(bot, chat_id: int, message_id: int, inline_markup: InlineKeyboardMarkup | None) -> None:
    if inline_markup is None:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=inline_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _edit_ui_message(
    bot,
    chat_id: int,
    message_id: int,
    text: str,
    inline_markup: InlineKeyboardMarkup | None,
) -> None:
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=inline_markup,
        parse_mode="HTML",
    )


async def _send_new_ui_message(
    bot,
    chat_id: int,
    text: str,
    *,
    inline_markup: InlineKeyboardMarkup | None,
    keep_menu: bool,
) -> int:
    sent = await bot.send_message(
        chat_id,
        text,
        reply_markup=inline_markup,
        parse_mode="HTML",
    )
    if keep_menu:
        await _ensure_reply_keyboard(bot, chat_id)
    return sent.message_id


async def show(
    *,
    bot,
    chat_id: int,
    user_id: int,
    text: str,
    reply_markup=None,
    user_message: Message | None = None,
    callback: CallbackQuery | None = None,
    with_main_menu: bool = False,
    keep_menu: bool = True,
) -> int | None:
    """Показать или обновить единственное UI-сoобщение бота в чате."""
    async with _lock_for(user_id):
        await delete_user_message(user_message)

        inline_markup = _inline_markup(reply_markup)
        stored_id = await _get_ui_message_id(user_id)

        edit_id: int | None = None
        if callback and callback.message:
            edit_id = callback.message.message_id
            if callback.message.photo or callback.message.document:
                await _delete_message(bot, chat_id, edit_id)
                if stored_id == edit_id:
                    stored_id = None
                edit_id = None
        if edit_id is None:
            edit_id = stored_id

        if edit_id and not with_main_menu:
            try:
                if callback and callback.message and not callback.message.photo and not callback.message.document:
                    await callback.message.edit_text(
                        text,
                        reply_markup=inline_markup,
                        parse_mode="HTML",
                    )
                else:
                    await _edit_ui_message(bot, chat_id, edit_id, text, inline_markup)
                await _set_ui_message_id(user_id, edit_id)
                return edit_id
            except TelegramBadRequest as exc:
                err = str(exc).lower()
                if "message is not modified" in err:
                    try:
                        await _apply_inline_markup(bot, chat_id, edit_id, inline_markup)
                    except Exception:
                        pass
                    await _set_ui_message_id(user_id, edit_id)
                    return edit_id
                await _delete_message(bot, chat_id, edit_id)
                if stored_id == edit_id:
                    stored_id = None
            except Exception:
                await _delete_message(bot, chat_id, edit_id)
                if stored_id == edit_id:
                    stored_id = None

        if stored_id:
            await _delete_message(bot, chat_id, stored_id)

        if with_main_menu:
            sent = await bot.send_message(
                chat_id,
                text,
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
            await _set_ui_message_id(user_id, sent.message_id)
            return sent.message_id

        message_id = await _send_new_ui_message(
            bot,
            chat_id,
            text,
            inline_markup=inline_markup,
            keep_menu=keep_menu,
        )
        await _set_ui_message_id(user_id, message_id)
        return message_id


async def show_from_message(
    message: Message,
    user_id: int,
    text: str,
    reply_markup=None,
    *,
    with_main_menu: bool = False,
    delete_user: bool = True,
    keep_menu: bool = True,
) -> int | None:
    return await show(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        text=text,
        reply_markup=reply_markup,
        user_message=message if delete_user else None,
        with_main_menu=with_main_menu,
        keep_menu=keep_menu,
    )


async def show_from_callback(
    callback: CallbackQuery,
    user_id: int,
    text: str,
    reply_markup=None,
    *,
    keep_menu: bool = True,
) -> int | None:
    if callback.message is None:
        return None
    return await show(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        user_id=user_id,
        text=text,
        reply_markup=reply_markup,
        callback=callback,
        keep_menu=keep_menu,
    )


async def show_photo(
    callback: CallbackQuery,
    user_id: int,
    photo,
    caption: str,
    reply_markup=None,
    *,
    keep_menu: bool = True,
) -> None:
    if callback.message is None:
        return

    async with _lock_for(user_id):
        chat_id = callback.message.chat.id

        stored_id = await _get_ui_message_id(user_id)
        await _delete_message(callback.bot, chat_id, callback.message.message_id)
        if stored_id and stored_id != callback.message.message_id:
            await _delete_message(callback.bot, chat_id, stored_id)

        sent = await callback.bot.send_photo(
            chat_id,
            photo,
            caption=caption,
            reply_markup=_inline_markup(reply_markup) or reply_markup,
            parse_mode="HTML",
        )
        await _set_ui_message_id(user_id, sent.message_id)
        if keep_menu:
            await _ensure_reply_keyboard(callback.bot, chat_id)
