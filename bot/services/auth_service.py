import asyncio
import base64
import os
import random
import uuid
from io import BytesIO
from typing import Optional, Tuple

from PIL import Image
from pyrogram import Client
from pyrogram.errors import (
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    SessionPasswordNeeded,
)
from qrcode import QRCode

import config
from bot.utils.device_fingerprint import DeviceFingerprint, client_kwargs_from_fingerprint
from bot.utils.texts import DEFAULT_DISPLAY_NAME

DEFAULT_API_ID = config.TELEGRAM_API_ID
DEFAULT_API_HASH = config.TELEGRAM_API_HASH


async def _human_delay(min_sec: float, max_sec: float) -> None:
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def send_code_to_phone(
    phone_number: str,
    fingerprint: DeviceFingerprint,
    api_id: int = DEFAULT_API_ID,
    api_hash: str = DEFAULT_API_HASH,
) -> Tuple[Optional[Client], Optional[str], Optional[str]]:
    session_name = str(config.SESSIONS_DIR / f"temp_{uuid.uuid4().hex[:8]}")
    try:
        await _human_delay(1.0, 3.0)
        app = Client(
            session_name,
            **client_kwargs_from_fingerprint(api_id, api_hash, fingerprint=fingerprint, phone_number=phone_number),
        )
        await app.connect()
        sent_code = await app.send_code(phone_number)
        await _human_delay(2.0, 5.0)
        return app, sent_code.phone_code_hash, None
    except Exception as e:
        return None, None, f"Ошибка при отправке кода: {e}"


async def authorize_by_phone(
    phone_number: str,
    code: str,
    phone_code_hash: str,
    fingerprint: DeviceFingerprint,
    password: str | None = None,
    client: Client | None = None,
    api_id: int = DEFAULT_API_ID,
    api_hash: str = DEFAULT_API_HASH,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    should_disconnect = False
    app = client
    try:
        if app is None:
            session_name = str(config.SESSIONS_DIR / f"temp_{uuid.uuid4().hex[:8]}")
            app = Client(
                session_name,
                **client_kwargs_from_fingerprint(api_id, api_hash, fingerprint=fingerprint, phone_number=phone_number),
            )
            await app.connect()
            should_disconnect = True

        await _human_delay(3.0, 8.0)
        try:
            await app.sign_in(phone_number, phone_code_hash, code)
        except SessionPasswordNeeded:
            if not password:
                if should_disconnect:
                    await app.disconnect()
                return None, None, "PASSWORD_NEEDED"
            try:
                await app.check_password(password)
            except PasswordHashInvalid:
                if should_disconnect:
                    await app.disconnect()
                return None, None, "PASSWORD_HASH_INVALID"

        await _human_delay(1.0, 2.5)
        session_string = await app.export_session_string()
        me = await app.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (me.username or DEFAULT_DISPLAY_NAME)
        if should_disconnect:
            await app.disconnect()
        return session_string, name, None
    except PhoneCodeInvalid:
        if app and should_disconnect:
            await app.disconnect()
        return None, None, "Неверный код подтверждения"
    except PhoneCodeExpired:
        if app and should_disconnect:
            await app.disconnect()
        return None, None, "Код подтверждения истек"
    except FloodWait as e:
        if app and should_disconnect:
            await app.disconnect()
        return None, None, f"Слишком много попыток. Подождите {e.value} секунд"
    except Exception as e:
        if app and should_disconnect:
            await app.disconnect()
        return None, None, f"Ошибка авторизации: {e}"


async def generate_qr_code(
    fingerprint: DeviceFingerprint,
    api_id: int = DEFAULT_API_ID,
    api_hash: str = DEFAULT_API_HASH,
) -> Tuple[Optional[BytesIO], Optional[str], Optional[Client], Optional[asyncio.Event]]:
    app = None
    try:
        session_name = str(config.SESSIONS_DIR / f"qr_temp_{uuid.uuid4().hex[:8]}")
        app = Client(
            session_name,
            **client_kwargs_from_fingerprint(api_id, api_hash, fingerprint=fingerprint),
        )
        await app.connect()

        from pyrogram.handlers import RawUpdateHandler
        from pyrogram.raw.functions.auth import ExportLoginToken
        from pyrogram.raw.types import UpdateLoginToken

        login_token_event = asyncio.Event()

        async def handle_update_login_token(client, update, users, chats):
            if isinstance(update, UpdateLoginToken):
                login_token_event.set()

        app.add_handler(RawUpdateHandler(handle_update_login_token))

        result = await app.invoke(
            ExportLoginToken(api_id=api_id, api_hash=api_hash, except_ids=[])
        )

        if hasattr(result, "token"):
            token_b64 = base64.urlsafe_b64encode(result.token).decode("utf-8").rstrip("=")
            qr_url = f"tg://login?token={token_b64}"
            qr_code = QRCode(version=1, box_size=10, border=5)
            qr_code.add_data(qr_url)
            qr_code.make(fit=True)
            img = qr_code.make_image(fill_color="black", back_color="white")
            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            return img_bytes, token_b64, app, login_token_event

        await app.disconnect()
        return None, None, None, None
    except Exception:
        if app is not None:
            try:
                await app.disconnect()
            except Exception:
                pass
        return None, None, None, None


async def check_qr_authorized(
    client: Client,
    login_token_event: Optional[asyncio.Event] = None,
) -> Tuple[Optional[str], Optional[str], bool, Optional[str]]:
    from pyrogram.errors import SessionPasswordNeeded
    from pyrogram.raw.functions.auth import ExportLoginToken, ImportLoginToken
    from pyrogram.raw.types.auth import LoginTokenMigrateTo, LoginTokenSuccess

    try:
        try:
            me = await client.get_me()
            if me and me.id:
                session_string = await client.export_session_string()
                user_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or DEFAULT_DISPLAY_NAME
                return session_string, user_name, True, None
        except SessionPasswordNeeded:
            return None, None, False, "PASSWORD_NEEDED"
        except Exception:
            pass

        if login_token_event and login_token_event.is_set():
            result = await client.invoke(
                ExportLoginToken(api_id=DEFAULT_API_ID, api_hash=DEFAULT_API_HASH, except_ids=[])
            )
            if isinstance(result, LoginTokenSuccess):
                session_string = await client.export_session_string()
                me = await client.get_me()
                user_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or DEFAULT_DISPLAY_NAME
                return session_string, user_name, True, None
            if isinstance(result, LoginTokenMigrateTo):
                migrate_result = await client.invoke(ImportLoginToken(token=result.token))
                if isinstance(migrate_result, LoginTokenSuccess):
                    session_string = await client.export_session_string()
                    me = await client.get_me()
                    user_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or DEFAULT_DISPLAY_NAME
                    return session_string, user_name, True, None

        result = await client.invoke(
            ExportLoginToken(api_id=DEFAULT_API_ID, api_hash=DEFAULT_API_HASH, except_ids=[])
        )
        if isinstance(result, LoginTokenSuccess):
            session_string = await client.export_session_string()
            me = await client.get_me()
            user_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or DEFAULT_DISPLAY_NAME
            return session_string, user_name, True, None
        if isinstance(result, LoginTokenMigrateTo):
            migrate_result = await client.invoke(ImportLoginToken(token=result.token))
            if isinstance(migrate_result, LoginTokenSuccess):
                session_string = await client.export_session_string()
                me = await client.get_me()
                user_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or DEFAULT_DISPLAY_NAME
                return session_string, user_name, True, None

        return None, None, False, None
    except SessionPasswordNeeded:
        return None, None, False, "PASSWORD_NEEDED"
    except Exception:
        return None, None, False, None
