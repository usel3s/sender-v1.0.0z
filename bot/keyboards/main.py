from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.utils import emojis as E

MENU_BUTTONS = frozenset({"Профиль", "Аккаунт", "Люди", "Настройки", "Рассылка"})


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Профиль", icon_custom_emoji_id=E.PROFILE),
                KeyboardButton(text="Аккаунт", icon_custom_emoji_id=E.SETTINGS),
            ],
            [
                KeyboardButton(text="Люди", icon_custom_emoji_id=E.PEOPLE),
                KeyboardButton(text="Настройки", icon_custom_emoji_id=E.SETTINGS),
            ],
            [KeyboardButton(text="Рассылка", icon_custom_emoji_id=E.SEND_UP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def no_access_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запросить доступ",
                    callback_data="request_access",
                    icon_custom_emoji_id=E.BELL,
                )
            ]
        ]
    )


def back_button(callback_data: str = "admin_back") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="Назад", callback_data=callback_data, icon_custom_emoji_id=E.BACK)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Статистика",
                    callback_data="admin_stats",
                    icon_custom_emoji_id=E.CHART_STATS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Стартовое сообщение",
                    callback_data="admin_start_msg",
                    icon_custom_emoji_id=E.PENCIL,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Выдача доступа",
                    callback_data="admin_access",
                    icon_custom_emoji_id=E.LOCK_OPEN,
                )
            ],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button()]])


def account_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="По номеру телефона",
                    callback_data="auth_phone",
                    icon_custom_emoji_id=E.WRITE,
                )
            ],
            [
                InlineKeyboardButton(
                    text="По QR-коду",
                    callback_data="auth_qr",
                    icon_custom_emoji_id=E.EYE,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Сессия Telegram Desktop",
                    callback_data="auth_tdata",
                    icon_custom_emoji_id=E.FILE,
                )
            ],
            [back_button("menu_back")],
        ]
    )


def qr_check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Я отсканировал QR-код",
                    callback_data="auth_qr_check",
                    icon_custom_emoji_id=E.CHECK,
                )
            ],
            [back_button("auth_cancel")],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="КД между сообщениями",
                    callback_data="settings_delay",
                    icon_custom_emoji_id=E.CLOCK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Лимит в час",
                    callback_data="settings_hourly",
                    icon_custom_emoji_id=E.CHART_GROWTH,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Лимит в день",
                    callback_data="settings_daily",
                    icon_custom_emoji_id=E.CALENDAR,
                )
            ],
            [back_button("menu_back")],
        ]
    )


def broadcast_keyboard(running: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if not running:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Начать рассылку",
                    callback_data="broadcast_start",
                    icon_custom_emoji_id=E.SEND_UP,
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Остановить",
                    callback_data="broadcast_stop",
                    icon_custom_emoji_id=E.CROSS,
                )
            ]
        )
    rows.append([back_button("menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(yes_data: str, no_data: str = "menu_back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить", callback_data=yes_data, icon_custom_emoji_id=E.CHECK),
                InlineKeyboardButton(text="Отмена", callback_data=no_data, icon_custom_emoji_id=E.CROSS),
            ]
        ]
    )
