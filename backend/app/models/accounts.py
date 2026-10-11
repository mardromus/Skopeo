"""Accounts and notifications: users, notification channels, rules and the delivery log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="google")  # google | local
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationChannel(UUIDPrimaryKey, Timestamped, Base):
    """Where a user wants to be told things: an email address or a webhook."""

    __tablename__ = "notification_channels"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # email | slack | discord | webhook
    name: Mapped[str] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(Text)  # email address or webhook URL (webhook URLs are secrets: never returned in full)
    signing_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationRule(UUIDPrimaryKey, Timestamped, Base):
    """When to notify: an event, optional filters, and the channels to use."""

    __tablename__ = "notification_rules"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    channel_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationDelivery(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "notification_deliveries"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    rule_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent | failed | skipped | dry_run
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
