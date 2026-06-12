import asyncio
import random
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, PeerFlood, UserPrivacyRestricted, UsernameInvalid, UsernameNotOccupied
from sqlalchemy import select

import config
from bot.services.account_service import parse_id_list
from bot.utils.device_fingerprint import DeviceFingerprint, client_kwargs_from_fingerprint
from database.database import async_session
from database.models import Account, BroadcastJob, UserSettings


def split_recipients(recipients: list[str], parts: int) -> list[list[str]]:
    if parts <= 0:
        return []
    if parts == 1:
        return [recipients]
    chunks: list[list[str]] = [[] for _ in range(parts)]
    for index, recipient in enumerate(recipients):
        chunks[index % parts].append(recipient)
    return chunks


class BroadcastManager:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._cancel_flags: dict[int, bool] = {}
        self._quota_locks: dict[int, asyncio.Lock] = {}

    def is_running(self, user_id: int) -> bool:
        task = self._tasks.get(user_id)
        return task is not None and not task.done()

    def active_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def stop(self, user_id: int) -> None:
        self._cancel_flags[user_id] = True
        task = self._tasks.get(user_id)
        if task and not task.done():
            task.cancel()

    async def start(
        self,
        user_id: int,
        job_id: int,
        recipients: list[str],
        message_html: str,
        progress_callback,
        account_ids: list[int],
    ) -> None:
        if self.is_running(user_id):
            raise RuntimeError("Рассылка уже запущена")
        if not account_ids:
            raise RuntimeError("Не выбран ни один аккаунт")
        self._cancel_flags[user_id] = False
        self._quota_locks[user_id] = asyncio.Lock()
        self._tasks[user_id] = asyncio.create_task(
            self._run_multi(user_id, job_id, recipients, message_html, progress_callback, account_ids)
        )

    async def _run_multi(
        self,
        user_id: int,
        job_id: int,
        recipients: list[str],
        message_html: str,
        progress_callback,
        account_ids: list[int],
    ) -> None:
        chunks = split_recipients(recipients, len(account_ids))
        progress = {"sent": 0, "failed": 0}
        status_holder = {"status": "running"}

        async with async_session() as session:
            job = await session.get(BroadcastJob, job_id)
            db_user_id = job.user_id if job else user_id
            if job:
                job.status = "running"
                job.total = len(recipients)
                await session.commit()

        try:
            await asyncio.gather(
                *[
                    self._run_account(
                        user_id=user_id,
                        job_id=job_id,
                        account_id=account_id,
                        db_user_id=db_user_id,
                        recipients=chunk,
                        message_html=message_html,
                        progress=progress,
                        status_holder=status_holder,
                        progress_callback=progress_callback,
                        total=len(recipients),
                    )
                    for account_id, chunk in zip(account_ids, chunks)
                    if chunk
                ]
            )
        except asyncio.CancelledError:
            status_holder["status"] = "cancelled"
        finally:
            async with async_session() as session:
                job = await session.get(BroadcastJob, job_id)
                if job:
                    if self._cancel_flags.get(user_id):
                        job.status = "cancelled"
                    elif status_holder["status"] == "peer_flood":
                        job.status = "peer_flood"
                    elif status_holder["status"] == "quota_reached":
                        job.status = "quota_reached"
                    elif job.status == "running":
                        job.status = "completed"
                    job.sent_count = progress["sent"]
                    job.failed_count = progress["failed"]
                    await session.commit()
                    await progress_callback(
                        progress["sent"],
                        progress["failed"],
                        len(recipients),
                        job.status,
                    )

            self._tasks.pop(user_id, None)
            self._cancel_flags.pop(user_id, None)
            self._quota_locks.pop(user_id, None)

    async def _run_account(
        self,
        *,
        user_id: int,
        job_id: int,
        account_id: int,
        db_user_id: int,
        recipients: list[str],
        message_html: str,
        progress: dict,
        status_holder: dict,
        progress_callback,
        total: int,
    ) -> None:
        async with async_session() as session:
            account = await session.get(Account, account_id)
            if account is None:
                return

            fingerprint = DeviceFingerprint(
                device_model=account.device_model or "Samsung SM-G991B",
                system_version=account.system_version or "SDK 33",
                app_version=account.app_version or "10.14.5",
                lang_code=account.lang_code or "ru",
            )

            client = Client(
                f"broadcast_{user_id}_{account_id}",
                session_string=account.session_string,
                **client_kwargs_from_fingerprint(
                    config.TELEGRAM_API_ID,
                    config.TELEGRAM_API_HASH,
                    fingerprint=fingerprint,
                ),
            )

        try:
            await client.start()
            for recipient in recipients:
                if self._cancel_flags.get(user_id) or status_holder["status"] != "running":
                    break

                if not await self._check_quota(user_id, db_user_id):
                    status_holder["status"] = "quota_reached"
                    break

                delay = max(30, await self._get_delay(db_user_id) + random.randint(-15, 30))
                await asyncio.sleep(delay)

                sent_ok = False
                try:
                    chat_id = recipient.lstrip("@")
                    try:
                        await client.read_chat_history(chat_id, max_id=0)
                    except Exception:
                        pass
                    await client.send_chat_action(chat_id, ChatAction.TYPING)
                    await asyncio.sleep(random.uniform(3, 8))
                    await client.send_message(chat_id, message_html)
                    sent_ok = True
                except FloodWait as exc:
                    await asyncio.sleep(exc.value + random.randint(2, 5))
                    try:
                        await client.send_message(recipient.lstrip("@"), message_html)
                        sent_ok = True
                    except Exception:
                        pass
                except PeerFlood:
                    status_holder["status"] = "peer_flood"
                    async with self._quota_locks[user_id]:
                        progress["failed"] += 1
                    await self._report_progress(progress, progress_callback, total, status_holder["status"])
                    break
                except (UserPrivacyRestricted, UsernameInvalid, UsernameNotOccupied):
                    pass
                except Exception:
                    pass

                async with self._quota_locks[user_id]:
                    if sent_ok:
                        progress["sent"] += 1
                        await self._increment_quota(user_id, db_user_id)
                    else:
                        progress["failed"] += 1
                    await self._persist_job(job_id, progress["sent"], progress["failed"])
                await self._report_progress(progress, progress_callback, total, status_holder["status"])
        finally:
            try:
                await client.stop()
            except Exception:
                pass

    async def _get_delay(self, db_user_id: int) -> int:
        async with async_session() as session:
            settings = (
                await session.execute(select(UserSettings).where(UserSettings.user_id == db_user_id))
            ).scalar_one_or_none()
            return settings.message_delay_sec if settings else 60

    async def _report_progress(self, progress: dict, progress_callback, total: int, status: str) -> None:
        await progress_callback(progress["sent"], progress["failed"], total, status)

    async def _persist_job(self, job_id: int, sent: int, failed: int) -> None:
        async with async_session() as session:
            job = await session.get(BroadcastJob, job_id)
            if job:
                job.sent_count = sent
                job.failed_count = failed
                await session.commit()

    async def _check_quota(self, tg_user_id: int, db_user_id: int) -> bool:
        lock = self._quota_locks.get(tg_user_id)
        if lock is None:
            return True
        async with lock:
            async with async_session() as session:
                settings = (
                    await session.execute(select(UserSettings).where(UserSettings.user_id == db_user_id))
                ).scalar_one_or_none()
                if settings is None:
                    return True

                now = datetime.utcnow()
                day_key = now.strftime("%Y-%m-%d")
                hour_key = now.strftime("%Y-%m-%d-%H")

                if settings.quota_day_key != day_key:
                    settings.quota_day_key = day_key
                    settings.quota_day_count = 0
                if settings.quota_hour_slot != hour_key:
                    settings.quota_hour_slot = hour_key
                    settings.quota_hour_count = 0

                if settings.quota_day_count >= settings.daily_limit:
                    return False
                if settings.quota_hour_count >= settings.hourly_limit:
                    return False
                return True

    async def _increment_quota(self, tg_user_id: int, db_user_id: int) -> None:
        lock = self._quota_locks.get(tg_user_id)
        if lock is None:
            return
        async with lock:
            await self._increment_quota_unlocked(db_user_id)

    async def _increment_quota_unlocked(self, db_user_id: int) -> None:
        async with async_session() as session:
            settings = (
                await session.execute(select(UserSettings).where(UserSettings.user_id == db_user_id))
            ).scalar_one_or_none()
            if settings is None:
                return
            now = datetime.utcnow()
            day_key = now.strftime("%Y-%m-%d")
            hour_key = now.strftime("%Y-%m-%d-%H")
            if settings.quota_day_key != day_key:
                settings.quota_day_key = day_key
                settings.quota_day_count = 0
            if settings.quota_hour_slot != hour_key:
                settings.quota_hour_slot = hour_key
                settings.quota_hour_count = 0
            settings.quota_day_count += 1
            settings.quota_hour_count += 1
            await session.commit()


def job_account_ids(job: BroadcastJob) -> list[int]:
    ids = parse_id_list(job.account_ids_json)
    if ids:
        return ids
    if job.account_id:
        return [job.account_id]
    return []


broadcast_manager = BroadcastManager()
