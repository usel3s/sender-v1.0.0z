import json
import re

from aiogram import F, Router
from aiogram.filters import BaseFilter, StateFilter
from aiogram.types import Message
from sqlalchemy import desc, select

from bot.keyboards.main import MENU_BUTTONS
from bot.services import chat_ui
from bot.states import AccountStates
from bot.utils import emojis as E
from database.database import async_session
from database.models import RecipientList, User

router = Router()


def parse_recipients(text: str) -> list[str]:
    recipients = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("@"):
            recipients.append(line)
        elif line.isdigit():
            recipients.append(line)
        elif re.match(r"^[\w\d_]{5,}$", line):
            recipients.append(f"@{line}")
    return list(dict.fromkeys(recipients))


class RecipientListFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text in MENU_BUTTONS or message.text.startswith("/"):
            return False
        return bool(parse_recipients(message.text))


@router.message(F.text == "Люди")
async def menu_people(message: Message, db_user: User) -> None:
    async with async_session() as session:
        last_list = (
            await session.execute(
                select(RecipientList)
                .where(RecipientList.user_id == db_user.id)
                .order_by(desc(RecipientList.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    count = 0
    if last_list:
        count = len(json.loads(last_list.recipients_json))

    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.PEOPLE, '👥')} <b>Список получателей</b>\n\n"
        f"Текущий список: <b>{count}</b> чел.\n\n"
        "Отправьте .txt файл или текст (по одному @username или id на строку).",
    )


@router.message(F.document)
async def people_document(message: Message, db_user: User, state) -> None:
    if await state.get_state() == AccountStates.waiting_tdata:
        return
    if not message.document.file_name.endswith(".txt"):
        return

    file = await message.bot.download(message.document)
    content = file.read().decode("utf-8", errors="ignore")
    await _save_recipients(message, db_user, content, message.document.file_name)


@router.message(RecipientListFilter(), StateFilter(None))
async def people_text(message: Message, db_user: User) -> None:
    await _save_recipients(message, db_user, message.text, "ручной_ввод.txt")


async def _save_recipients(message: Message, db_user: User, content: str, filename: str) -> None:
    recipients = parse_recipients(content)
    if not recipients:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Не найдено получателей в файле.",
        )
        return

    async with async_session() as session:
        session.add(
            RecipientList(
                user_id=db_user.id,
                filename=filename,
                recipients_json=json.dumps(recipients, ensure_ascii=False),
            )
        )
        await session.commit()

    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Список сохранён: <b>{len(recipients)}</b> получателей.",
    )
