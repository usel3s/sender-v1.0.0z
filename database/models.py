from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_access: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False)
    accounts: Mapped[list["Account"]] = relationship(back_populates="user")
    recipient_lists: Mapped[list["RecipientList"]] = relationship(back_populates="user")
    broadcast_jobs: Mapped[list["BroadcastJob"]] = relationship(back_populates="user")


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    start_message_html: Mapped[str] = mapped_column(Text, default="")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    message_delay_sec: Mapped[int] = mapped_column(Integer, default=60)
    daily_limit: Mapped[int] = mapped_column(Integer, default=40)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=10)
    quota_day_key: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quota_day_count: Mapped[int] = mapped_column(Integer, default=0)
    quota_hour_slot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quota_hour_count: Mapped[int] = mapped_column(Integer, default=0)
    ui_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="settings")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    session_string: Mapped[str] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lang_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="accounts")
    broadcast_jobs: Mapped[list["BroadcastJob"]] = relationship(back_populates="account")


class RecipientList(Base):
    __tablename__ = "recipient_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    recipients_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="recipient_lists")


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    message_html: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="broadcast_jobs")
    account: Mapped["Account"] = relationship(back_populates="broadcast_jobs")
