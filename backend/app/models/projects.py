"""Projects (the user's own software, as context) and watches on upstream open-source repositories."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow


class Project(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")
    """Free-text context from the user: how and where they use their dependencies."""
    source: Mapped[str] = mapped_column(String(16), default="upload")  # github | upload
    repository_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    branch: Mapped[str] = mapped_column(String(256), default="main")
    github_private: Mapped[bool] = mapped_column(Boolean, default=False)
    """Private repository: cloned with the owner's connected GitHub token."""
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectFile(UUIDPrimaryKey, Timestamped, Base):
    """A file the user uploaded as context (manifests and the code that uses a library)."""

    __tablename__ = "project_files"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))


class Watch(UUIDPrimaryKey, Timestamped, Base):
    """An upstream repository the user's project depends on, checked on a schedule."""

    __tablename__ = "watches"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    upstream_url: Mapped[str] = mapped_column(String(512))
    upstream_name: Mapped[str] = mapped_column(String(256))
    branch: Mapped[str | None] = mapped_column(String(256), nullable=True)  # None = default branch
    package_name: Mapped[str | None] = mapped_column(String(214), nullable=True)
    import_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    ecosystem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    frequency: Mapped[str] = mapped_column(String(16), default="daily")  # hourly | daily | weekly | manual
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | checking | ok | failed
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_seen_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Public API surface of the upstream at last_seen_sha: what the next check diffs against."""


class WatchReport(UUIDPrimaryKey, Timestamped, Base):
    """What changed upstream between two refs, and where it touches the user's project."""

    __tablename__ = "watch_reports"

    watch_id: Mapped[str] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="update")  # baseline | update
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | schedule
    base_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    impact_level: Mapped[str] = mapped_column(String(16), default="none")  # none | low | medium | high | breaking
    summary: Mapped[str] = mapped_column(Text, default="")
    narrative: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    commits: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    upstream_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    impacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    usages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
