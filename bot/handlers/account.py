import asyncio
import shutil
import uuid
import zipfile

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import account_method_keyboard, qr_check_keyboard
from bot.services import chat_ui
from bot.services.auth_service import authorize_by_phone, check_qr_authorized, generate_qr_code, send_code_to_phone
from bot.services.tdata_service import extract_tdata_root, import_tdata_to_session_string
from bot.states import AccountStates
from bot.utils import emojis as E
from bot.utils.device_fingerprint import DeviceFingerprint, generate_fingerprint
from bot.utils.rate_limit import LIMITS, rate_limiter
from bot.utils.texts import DEFAULT_DISPLAY_NAME
from database.database import async_session
from database.models import Account, User

router = Router()

_phone_clients: dict[int, object] = {}
_qr_clients: dict[int, object] = {}
_qr_events: dict[int, asyncio.Event] = {}


def _account_menu_text() -> str:
    return f"{E.e(E.SETTINGS, '⚙️')} <b>Подключение аккаунта</b>\n\nВыберите способ входа:"


async def save_account(db_user: User, session_string: str, name: str, phone: str | None, fingerprint) -> None:
    async with async_session() as session:
        existing = (
            await session.execute(select(Account).where(Account.user_id == db_user.id))
        ).scalar_one_or_none()
        if existing:
            existing.session_string = session_string
            existing.name = name
            existing.phone_number = phone
            existing.device_model = fingerprint.device_model
            existing.system_version = fingerprint.system_version
            existing.app_version = fingerprint.app_version
            existing.lang_code = fingerprint.lang_code
            existing.status = "active"
        else:
            session.add(
                Account(
                    user_id=db_user.id,
                    session_string=session_string,
                    name=name,
                    phone_number=phone,
                    device_model=fingerprint.device_model,
                    system_version=fingerprint.system_version,
                    app_version=fingerprint.app_version,
                    lang_code=fingerprint.lang_code,
                    status="active",
                )
            )
        await session.commit()


@router.message(F.text == "Аккаунт")
async def menu_account(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        _account_menu_text(),
        reply_markup=account_method_keyboard(),
    )


@router.callback_query(F.data == "auth_cancel")
async def auth_cancel(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    uid = callback.from_user.id
    if uid in _phone_clients:
        try:
            await _phone_clients[uid].disconnect()
        except Exception:
            pass
        _phone_clients.pop(uid, None)
    if uid in _qr_clients:
        try:
            await _qr_clients[uid].disconnect()
        except Exception:
            pass
        _qr_clients.pop(uid, None)
    _qr_events.pop(uid, None)
    await state.clear()
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        _account_menu_text(),
        reply_markup=account_method_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "auth_phone")
async def auth_phone(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    ok, retry = rate_limiter.check("add_account_start", callback.from_user.id, *LIMITS["add_account_start"])
    if not ok:
        await callback.answer(f"Подождите {retry} сек.", show_alert=True)
        return
    fingerprint = generate_fingerprint()
    await state.update_data(fingerprint=fingerprint.__dict__)
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.WRITE, '✍')} Отправьте номер телефона в формате <code>+79991234567</code>",
        reply_markup=account_method_keyboard(),
    )
    await state.set_state(AccountStates.waiting_phone)
    await callback.answer()


@router.message(AccountStates.waiting_phone)
async def auth_phone_received(message: Message, state: FSMContext, db_user: User) -> None:
    phone = (message.text or "").strip()
    if not phone.startswith("+") or len(phone) < 10:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Неверный формат номера.",
            reply_markup=account_method_keyboard(),
        )
        return

    ok, retry = rate_limiter.check("request_code", message.from_user.id, *LIMITS["request_code"])
    if not ok:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"Подождите {retry} сек. перед повторным запросом кода.",
            reply_markup=account_method_keyboard(),
        )
        return

    data = await state.get_data()
    fingerprint = DeviceFingerprint(**data["fingerprint"])
    client, phone_code_hash, error = await send_code_to_phone(phone, fingerprint)
    if error:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} {error}",
            reply_markup=account_method_keyboard(),
        )
        return

    _phone_clients[message.from_user.id] = client
    await state.update_data(phone=phone, phone_code_hash=phone_code_hash)
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.BELL, '🔔')} Код отправлен. Введите код из Telegram:",
        reply_markup=account_method_keyboard(),
    )
    await state.set_state(AccountStates.waiting_code)


@router.message(AccountStates.waiting_code)
async def auth_code_received(message: Message, state: FSMContext, db_user: User) -> None:
    ok, retry = rate_limiter.check("code_entry", message.from_user.id, *LIMITS["code_entry"])
    if not ok:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"Подождите {retry} сек.",
            reply_markup=account_method_keyboard(),
        )
        return

    code = (message.text or "").strip().replace(" ", "").replace("-", "")
    data = await state.get_data()
    fingerprint = DeviceFingerprint(**data["fingerprint"])
    client = _phone_clients.get(message.from_user.id)
    session_string, name, error = await authorize_by_phone(
        phone_number=data["phone"],
        code=code,
        phone_code_hash=data["phone_code_hash"],
        fingerprint=fingerprint,
        client=client,
    )
    _phone_clients.pop(message.from_user.id, None)

    if error == "PASSWORD_NEEDED":
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.LOCK_CLOSED, '🔒')} Введите пароль двухфакторной защиты:",
            reply_markup=account_method_keyboard(),
        )
        await state.set_state(AccountStates.waiting_password)
        return

    if error or not session_string:
        await state.clear()
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} {error or 'Ошибка авторизации'}",
            reply_markup=account_method_keyboard(),
        )
        return

    await save_account(db_user, session_string, name, data["phone"], fingerprint)
    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Аккаунт <b>{name}</b> успешно подключён!",
        reply_markup=account_method_keyboard(),
    )


@router.message(AccountStates.waiting_password)
async def auth_password_received(message: Message, state: FSMContext, db_user: User) -> None:
    from pyrogram.errors import PasswordHashInvalid

    password = message.text or ""
    data = await state.get_data()
    fingerprint = DeviceFingerprint(**data["fingerprint"])
    client = _phone_clients.get(message.from_user.id)
    if not client:
        await state.clear()
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Сессия истекла. Начните заново.",
            reply_markup=account_method_keyboard(),
        )
        return

    try:
        await client.check_password(password)
        session_string = await client.export_session_string()
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (me.username or DEFAULT_DISPLAY_NAME)
        await client.disconnect()
    except PasswordHashInvalid:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Неверный пароль.",
            reply_markup=account_method_keyboard(),
        )
        return
    except Exception as e:
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CROSS, '❌')} Ошибка: {e}",
            reply_markup=account_method_keyboard(),
        )
        return
    finally:
        _phone_clients.pop(message.from_user.id, None)

    await save_account(db_user, session_string, name, data["phone"], fingerprint)
    await state.clear()
    await chat_ui.show_from_message(
        message,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Аккаунт <b>{name}</b> успешно подключён!",
        reply_markup=account_method_keyboard(),
    )


@router.callback_query(F.data == "auth_qr")
async def auth_qr(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    ok, retry = rate_limiter.check("add_account_start", callback.from_user.id, *LIMITS["add_account_start"])
    if not ok:
        await callback.answer(f"Подождите {retry} сек.", show_alert=True)
        return

    fingerprint = generate_fingerprint()
    await state.update_data(fingerprint=fingerprint.__dict__)
    img_bytes, token, client, event = await generate_qr_code(fingerprint)
    if not img_bytes:
        await callback.answer("Не удалось создать QR-код", show_alert=True)
        return

    _qr_clients[callback.from_user.id] = client
    _qr_events[callback.from_user.id] = event
    photo = BufferedInputFile(img_bytes.read(), filename="qr.png")
    await chat_ui.show_photo(
        callback,
        db_user.id,
        photo,
        f"{E.e(E.EYE, '👁')} Отсканируйте QR-код в Telegram → Настройки → Устройства → Подключить.",
        reply_markup=qr_check_keyboard(),
    )
    await state.set_state(AccountStates.waiting_qr)
    await callback.answer()


@router.callback_query(F.data == "auth_qr_check")
async def auth_qr_check(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    client = _qr_clients.get(callback.from_user.id)
    event = _qr_events.get(callback.from_user.id)
    if not client:
        await callback.answer("QR-сессия истекла", show_alert=True)
        return

    session_string, name, authorized, error = await check_qr_authorized(client, event)
    if error == "PASSWORD_NEEDED":
        await callback.answer("Требуется пароль двухфакторной защиты на устройстве", show_alert=True)
        return
    if not authorized or not session_string:
        await callback.answer("QR ещё не отсканирован", show_alert=True)
        return

    data = await state.get_data()
    fingerprint = DeviceFingerprint(**data.get("fingerprint", generate_fingerprint().__dict__))
    try:
        await client.disconnect()
    except Exception:
        pass
    _qr_clients.pop(callback.from_user.id, None)
    _qr_events.pop(callback.from_user.id, None)

    await save_account(db_user, session_string, name, None, fingerprint)
    await state.clear()
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.CHECK, '✅')} Аккаунт <b>{name}</b> успешно подключён через QR!",
        reply_markup=account_method_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "auth_tdata")
async def auth_tdata(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    ok, retry = rate_limiter.check("tdata_import", callback.from_user.id, *LIMITS["tdata_import"])
    if not ok:
        await callback.answer(f"Подождите {retry} сек.", show_alert=True)
        return
    fingerprint = generate_fingerprint()
    await state.update_data(fingerprint=fingerprint.__dict__)
    await chat_ui.show_from_callback(
        callback,
        db_user.id,
        f"{E.e(E.FILE, '📁')} Отправьте ZIP-архив с папкой <code>tdata</code> из Telegram Desktop.",
        reply_markup=account_method_keyboard(),
    )
    await state.set_state(AccountStates.waiting_tdata)
    await callback.answer()


@router.message(AccountStates.waiting_tdata, F.document)
async def auth_tdata_received(message: Message, state: FSMContext, db_user: User) -> None:
    import config

    data = await state.get_data()
    fingerprint = DeviceFingerprint(**data["fingerprint"])
    extract_dir = config.SESSIONS_DIR / f"tdata_extract_{uuid.uuid4().hex[:8]}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        await message.bot.download(message.document, destination=extract_dir / "upload.zip")
        zip_path = extract_dir / "upload.zip"
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        tdata_root = extract_tdata_root(extract_dir)
        if not tdata_root:
            await chat_ui.show_from_message(
                message,
                db_user.id,
                f"{E.e(E.CROSS, '❌')} Папка сессии не найдена в архиве.",
                reply_markup=account_method_keyboard(),
            )
            return

        tdata_path = tdata_root / "tdata" if (tdata_root / "tdata").is_dir() else tdata_root
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.LOADING, '🔄')} Импорт сессии Telegram Desktop...",
            reply_markup=account_method_keyboard(),
        )

        session_string, name, phone, error = await import_tdata_to_session_string(tdata_path, fingerprint)
        if error or not session_string:
            await chat_ui.show_from_message(
                message,
                db_user.id,
                f"{E.e(E.CROSS, '❌')} {error or 'Ошибка импорта'}",
                reply_markup=account_method_keyboard(),
            )
            return

        await save_account(db_user, session_string, name, phone, fingerprint)
        await state.clear()
        await chat_ui.show_from_message(
            message,
            db_user.id,
            f"{E.e(E.CHECK, '✅')} Аккаунт <b>{name}</b> импортирован из Telegram Desktop!",
            reply_markup=account_method_keyboard(),
        )
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
