import shutil
import uuid
from pathlib import Path

import config
from bot.utils.device_fingerprint import DeviceFingerprint, client_kwargs_from_fingerprint
from bot.utils.texts import DEFAULT_DISPLAY_NAME


def _resolve_tdata_folder(path: Path) -> Path:
    if path.name == "tdata":
        return path
    nested = path / "tdata"
    if nested.is_dir():
        return nested
    return path


def _tdata_error_message(exc: Exception) -> str:
    try:
        from tdata_reader.exceptions import TDataBadDecryptKey, TDataCorrupted, TDataFileNotFound
    except ImportError:
        return f"Установите зависимость: pip install tdata-reader ({exc})"

    if isinstance(exc, TDataBadDecryptKey):
        return "TData защищён паролем. Отключите локальный пароль в Telegram Desktop и экспортируйте снова."
    if isinstance(exc, TDataFileNotFound):
        return "Файлы TData не найдены. В ZIP должна быть папка tdata из Telegram Desktop."
    if isinstance(exc, TDataCorrupted):
        return "TData повреждён или имеет неподдерживаемый формат."
    return f"Ошибка импорта TData: {exc}"


async def import_tdata_to_session_string(
    tdata_path: Path,
    fingerprint: DeviceFingerprint,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Конвертация TData → Pyrogram session string (без PyQt5/opentele)."""
    try:
        from pyrogram import Client
        from pyrogram.session.internals import AuthKey
        from tdata_reader import read_tdata
    except ImportError as exc:
        return None, None, None, f"Установите зависимости: pip install -r requirements.txt ({exc})"

    pyro_session_name = str(config.SESSIONS_DIR / f"tdata_py_{uuid.uuid4().hex[:8]}")
    pyro_client = None

    try:
        account = read_tdata(str(_resolve_tdata_folder(tdata_path)))

        pyro_client = Client(
            pyro_session_name,
            in_memory=True,
            **client_kwargs_from_fingerprint(
                config.TELEGRAM_API_ID,
                config.TELEGRAM_API_HASH,
                fingerprint=fingerprint,
            ),
        )
        await pyro_client.connect()
        await pyro_client.storage.dc_id(account.dc_id)
        await pyro_client.storage.auth_key(AuthKey(account.auth_key))
        await pyro_client.storage.user_id(account.user_id)
        await pyro_client.storage.is_bot(False)
        await pyro_client.storage.date(0)
        await pyro_client.storage.test_mode(False)
        await pyro_client.storage.save()

        session_string = await pyro_client.export_session_string()
        me = await pyro_client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (me.username or DEFAULT_DISPLAY_NAME)
        phone = me.phone_number
        await pyro_client.disconnect()
        pyro_client = None

        return session_string, name, phone, None
    except Exception as exc:
        return None, None, None, _tdata_error_message(exc)
    finally:
        if pyro_client is not None:
            try:
                await pyro_client.disconnect()
            except Exception:
                pass


def extract_tdata_root(extracted_dir: Path) -> Path | None:
    if (extracted_dir / "tdata").is_dir():
        return extracted_dir
    if extracted_dir.name == "tdata":
        return extracted_dir.parent
    for child in extracted_dir.rglob("tdata"):
        if child.is_dir() and any(child.iterdir()):
            return child.parent if child.name == "tdata" else child
    return None
