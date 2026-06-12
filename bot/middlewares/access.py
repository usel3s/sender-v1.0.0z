from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import config
from bot.keyboards.main import MENU_BUTTONS
from database.database import async_session, get_or_create_user


class AccessMiddleware(BaseMiddleware):
    ALLOWED_COMMANDS = {"/start", "/admin"}
    ALLOWED_CALLBACKS = {
        "request_access",
        "menu_back",
        "admin_back",
        "admin_stats",
        "admin_start_msg",
        "admin_access",
        "admin_start_confirm",
        "admin_start_cancel",
        "admin_toggle_access",
        "admin_toggle_admin",
        "admin_search_user",
    }
    ALLOWED_CALLBACK_PREFIXES = (
        "admin_toggle_",
        "admin_user_",
        "admin_",
        "settings_",
        "broadcast_",
        "auth_",
        "account_",
        "menu_back",
    )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        async with async_session() as session:
            db_user = await get_or_create_user(session, user.id, user.username)
            data["db_user"] = db_user

        if db_user.is_admin or db_user.tg_id in config.ADMIN_IDS:
            return await handler(event, data)

        if isinstance(event, Message) and event.text:
            if event.text.split()[0] in self.ALLOWED_COMMANDS:
                return await handler(event, data)
            if event.text in MENU_BUTTONS:
                if not db_user.has_access:
                    await self._deny(event, db_user)
                    return None

        if isinstance(event, CallbackQuery) and event.data:
            if event.data in self.ALLOWED_CALLBACKS or event.data.startswith(self.ALLOWED_CALLBACK_PREFIXES):
                return await handler(event, data)
            if event.data == "request_access":
                return await handler(event, data)
            if not db_user.has_access:
                await event.answer("Нет доступа к боту", show_alert=True)
                return None

        if not db_user.has_access and isinstance(event, Message):
            if event.text and not event.text.startswith("/"):
                await self._deny(event, db_user)
                return None

        return await handler(event, data)

    async def _deny(self, event: Message, db_user) -> None:
        from bot.keyboards.main import no_access_keyboard
        from bot.services import chat_ui
        from bot.utils import emojis as E

        await chat_ui.show_from_message(
            event,
            db_user.id,
            f"{E.e(E.LOCK_CLOSED, '🔒')} <b>Нет доступа</b>\n\nОбратитесь к администратору для получения доступа.",
            reply_markup=no_access_keyboard(),
            delete_user=event.text in MENU_BUTTONS,
            keep_menu=False,
        )
