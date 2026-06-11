"""Пользовательские тексты интерфейса бота."""

DEFAULT_DISPLAY_NAME = "Без имени"

YES = "да"
NO = "нет"


def yes_no(value: bool) -> str:
    return YES if value else NO


def access_toggle_label(has_access: bool) -> str:
    return "Отозвать доступ" if has_access else "Выдать доступ"


def admin_toggle_label(is_admin: bool) -> str:
    return "Снять админа" if is_admin else "Назначить админом"


BROADCAST_STATUS = {
    "running": "идёт",
    "completed": "завершена",
    "cancelled": "отменена",
    "pending": "ожидание",
    "peer_flood": "остановлена (ограничение Telegram)",
    "quota_reached": "остановлена (достигнут лимит)",
}


def broadcast_status_label(status: str) -> str:
    return BROADCAST_STATUS.get(status, "неизвестно")
