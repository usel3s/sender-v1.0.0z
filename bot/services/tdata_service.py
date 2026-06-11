import shutil
import uuid
from pathlib import Path

import config
from bot.utils.device_fingerprint import DeviceFingerprint, client_kwargs_from_fingerprint


async def import_tdata_to_session_string(
    tdata_path: Path,
    fingerprint: DeviceFingerprint,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Convert Telegram Desktop TData to Pyrogram session string via opentele + Telethon."""
    telethon_session_path = config.SESSIONS_DIR / f"tdata_tl_{uuid.uuid4().hex[:8]}"
    pyro_session_name = str(config.SESSIONS_DIR / f"tdata_py_{uuid.uuid4().hex[:8]}")

    try:
        from opentele.api import UseCurrentSession
        from opentele.td import TDesktop
        from pyrogram import Client
        from pyrogram.session.internals import AuthKey
    except ImportError as e:
        return None, None, None, f"Не установлены зависимости: {e}"

    telethon_client = None
    pyro_client = None
    try:
        if tdata_path.name == "tdata":
            desktop_path = tdata_path.parent
        else:
            desktop_path = tdata_path

        tdesk = TDesktop(str(desktop_path))
        if not tdesk.isLoaded():
            return None, None, None, "Не удалось загрузить TData. Проверьте папку tdata."

        telethon_client = await tdesk.ToTelethon(session=str(telethon_session_path), flag=UseCurrentSession)
        await telethon_client.connect()
        if not await telethon_client.is_user_authorized():
            return None, None, None, "TData не авторизован"

        me = await telethon_client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (me.username or DEFAULT_DISPLAY_NAME)
        phone = me.phone

        dc_id = telethon_client.session.dc_id
        auth_key = telethon_client.session.auth_key.key
        user_id = me.id
        await telethon_client.disconnect()
        telethon_client = None

        pyro_client = Client(
            pyro_session_name,
            in_memory=True,
            **client_kwargs_from_fingerprint(config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, fingerprint=fingerprint),
        )
        await pyro_client.connect()
        await pyro_client.storage.dc_id(dc_id)
        await pyro_client.storage.auth_key(AuthKey(auth_key))
        await pyro_client.storage.user_id(user_id)
        await pyro_client.storage.is_bot(False)
        await pyro_client.storage.date(0)
        await pyro_client.storage.test_mode(False)
        await pyro_client.storage.save()

        session_string = await pyro_client.export_session_string()
        await pyro_client.get_me()
        await pyro_client.disconnect()
        pyro_client = None

        return session_string, name, phone, None
    except Exception as e:
        return None, None, None, f"Ошибка импорта TData: {e}"
    finally:
        if telethon_client is not None:
            try:
                await telethon_client.disconnect()
            except Exception:
                pass
        if pyro_client is not None:
            try:
                await pyro_client.disconnect()
            except Exception:
                pass
        if telethon_session_path.exists():
            if telethon_session_path.is_file():
                telethon_session_path.unlink(missing_ok=True)
            else:
                shutil.rmtree(telethon_session_path, ignore_errors=True)


def extract_tdata_root(extracted_dir: Path) -> Path | None:
    if (extracted_dir / "tdata").is_dir():
        return extracted_dir
    if extracted_dir.name == "tdata":
        return extracted_dir.parent
    for child in extracted_dir.rglob("tdata"):
        if child.is_dir() and any(child.iterdir()):
            return child.parent if child.name == "tdata" else child
    return None
