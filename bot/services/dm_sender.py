import asyncio
import random
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, PeerFlood, UserPrivacyRestricted, UsernameInvalid, UsernameNotOccupied
from sqlalchemy import select

import config
from bot.utils.device_fingerprint import client_kwargs_from_fingerprint, generate_fingerprint
from database.database import async_session
from database.models import Account, BroadcastJob, UserSettings


class BroadcastManager:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._cancel_flags: dict[int, bool] = {}

    def is_running(self, user_id: int) -> bool:
        task = self._tasks.get(user_id)
        return task is not None and not task.done()

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

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
    ) -> None:
        if self.is_running(user_id):
            raise RuntimeError("Рассылка уже запущена")
        self._cancel_flags[user_id] = False
        self._tasks[user_id] = asyncio.create_task(
            self._run(user_id, job_id, recipients, message_html, progress_callback)
        )

    async def _run(self, user_id: int, job_id: int, recipients: list[str], message_html: str, progress_callback) -> None:
        async with async_session() as session:
            job = await session.get(BroadcastJob, job_id)
            account = await session.get(Account, job.account_id)
            settings_result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == job.user_id)
            )
            settings = settings_result.scalar_one()

            fingerprint = DeviceFingerprint(
                device_model=account.device_model or "Samsung SM-G991B",
                system_version=account.system_version or "SDK 33",
                app_version=account.app_version or "10.14.5",
                lang_code=account.lang_code or "ru",
            )

            client = Client(
                f"broadcast_{user_id}",
                session_string=account.session_string,
                **client_kwargs_from_fingerprint(config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, fingerprint=fingerprint),
            )

            job.status = "running"
            job.total = len(recipients)
            await session.commit()

            sent = 0
            failed = 0

            try:
                await client.start()
                for recipient in recipients:
                    if self._cancel_flags.get(user_id):
                        job.status = "cancelled"
                        break

                    if not self._check_quota(settings):
                        job.status = "quota_reached"
                        break

                    delay = settings.message_delay_sec + random.randint(-15, 30)
                    delay = max(30, delay)
                    await asyncio.sleep(delay)

                    try:
                        chat_id = recipient.lstrip("@")
                        try:
                            await client.read_chat_history(chat_id, max_id=0)
                        except Exception:
                            pass
                        await client.send_chat_action(chat_id, ChatAction.TYPING)
                        await asyncio.sleep(random.uniform(3, 8))
                        await client.send_message(chat_id, message_html)
                        sent += 1
                        self._increment_quota(settings)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + random.randint(2, 5))
                        try:
                            await client.send_message(recipient.lstrip("@"), message_html)
                            sent += 1
                            self._increment_quota(settings)
                        except Exception:
                            failed += 1
                    except PeerFlood:
                        job.status = "peer_flood"
                        failed += 1
                        break
                    except (UserPrivacyRestricted, UsernameInvalid, UsernameNotOccupied):
                        failed += 1
                    except Exception:
                        failed += 1

                    job.sent_count = sent
                    job.failed_count = failed
                    self._increment_quota(settings)
                    await session.commit()
                    await progress_callback(sent, failed, len(recipients), job.status)

                if job.status == "running":
                    job.status = "completed"
                job.sent_count = sent
                job.failed_count = failed
                await session.commit()
                await progress_callback(sent, failed, len(recipients), job.status)
            finally:
                try:
                    await client.stop()
                except Exception:
                    pass
                self._tasks.pop(user_id, None)
                self._cancel_flags.pop(user_id, None)

    def _check_quota(self, settings: UserSettings) -> bool:
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

    def _increment_quota(self, settings: UserSettings) -> None:
        settings.quota_day_count += 1
        settings.quota_hour_count += 1


broadcast_manager = BroadcastManager()
