"""Persistence for accounts, notifications, projects and watches.

Every read and write that takes a ``user_id`` is scoped to that user: a row owned by someone else
behaves exactly like a missing row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update

from app.database import session_scope
from app.models import (
    Investigation,
    NotificationChannel,
    NotificationDelivery,
    NotificationRule,
    Project,
    ProjectFile,
    User,
    Watch,
    WatchReport,
    utcnow,
)

LOCAL_USER_EMAIL = "local@skopeo.invalid"


class AccountStore:
    # ------------------------------------------------------------------ users
    def get_user(self, user_id: str) -> User | None:
        with session_scope() as s:
            return s.get(User, user_id)

    def upsert_firebase_user(self, claims: dict[str, Any]) -> User:
        uid = str(claims["sub"])
        provider = str((claims.get("firebase") or {}).get("sign_in_provider") or "google")
        fields = {
            "email": (claims.get("email") or None),
            "email_verified": bool(claims.get("email_verified", False)),
            "display_name": (claims.get("name") or None),
            "photo_url": (claims.get("picture") or None),
            "provider": provider.removesuffix(".com"),
            "last_login_at": utcnow(),
        }
        with session_scope(write=True) as s:
            user = s.scalars(select(User).where(User.firebase_uid == uid)).first()
            if user is None:
                user = User(firebase_uid=uid, **fields)
                s.add(user)
            else:
                for k, v in fields.items():
                    setattr(user, k, v)
            s.flush()
            return user

    def get_or_create_local_user(self) -> User:
        with session_scope() as s:
            user = s.scalars(select(User).where(User.provider == "local")).first()
            if user is not None:
                return user
        with session_scope(write=True) as s:
            user = s.scalars(select(User).where(User.provider == "local")).first()
            if user is None:
                user = User(provider="local", email=LOCAL_USER_EMAIL, email_verified=False, display_name="Local user")
                s.add(user)
                s.flush()
            return user

    def delete_user(self, user_id: str) -> None:
        with session_scope(write=True) as s:
            s.execute(update(Investigation).where(Investigation.owner_id == user_id).values(owner_id=None))
            for model in (WatchReport, Watch, ProjectFile, NotificationDelivery, NotificationRule, NotificationChannel):
                if model is ProjectFile:
                    project_ids = select(Project.id).where(Project.user_id == user_id)
                    s.execute(delete(ProjectFile).where(ProjectFile.project_id.in_(project_ids)))
                else:
                    s.execute(delete(model).where(model.user_id == user_id))
            s.execute(delete(Project).where(Project.user_id == user_id))
            s.execute(delete(User).where(User.id == user_id))

    # --------------------------------------------------------------- channels
    def add_channel(self, user_id: str, **fields: Any) -> NotificationChannel:
        with session_scope(write=True) as s:
            ch = NotificationChannel(user_id=user_id, **fields)
            s.add(ch)
            s.flush()
            return ch

    def get_channel(self, user_id: str, channel_id: str) -> NotificationChannel | None:
        with session_scope() as s:
            ch = s.get(NotificationChannel, channel_id)
            return ch if ch is not None and ch.user_id == user_id else None

    def list_channels(self, user_id: str) -> list[NotificationChannel]:
        with session_scope() as s:
            return list(
                s.scalars(
                    select(NotificationChannel).where(NotificationChannel.user_id == user_id).order_by(NotificationChannel.created_at)
                )
            )

    def update_channel(self, channel_id: str, **fields: Any) -> NotificationChannel:
        with session_scope(write=True) as s:
            ch = s.get(NotificationChannel, channel_id)
            assert ch is not None
            for k, v in fields.items():
                setattr(ch, k, v)
            s.flush()
            return ch

    def delete_channel(self, user_id: str, channel_id: str) -> bool:
        with session_scope(write=True) as s:
            ch = s.get(NotificationChannel, channel_id)
            if ch is None or ch.user_id != user_id:
                return False
            s.delete(ch)
            for rule in s.scalars(select(NotificationRule).where(NotificationRule.user_id == user_id)):
                if channel_id in (rule.channel_ids or []):
                    rule.channel_ids = [c for c in rule.channel_ids if c != channel_id]
            return True

    # ------------------------------------------------------------------ rules
    def add_rule(self, user_id: str, **fields: Any) -> NotificationRule:
        with session_scope(write=True) as s:
            rule = NotificationRule(user_id=user_id, **fields)
            s.add(rule)
            s.flush()
            return rule

    def get_rule(self, user_id: str, rule_id: str) -> NotificationRule | None:
        with session_scope() as s:
            rule = s.get(NotificationRule, rule_id)
            return rule if rule is not None and rule.user_id == user_id else None

    def list_rules(self, user_id: str, event: str | None = None) -> list[NotificationRule]:
        with session_scope() as s:
            q = select(NotificationRule).where(NotificationRule.user_id == user_id)
            if event:
                q = q.where(NotificationRule.event == event)
            return list(s.scalars(q.order_by(NotificationRule.created_at)))

    def update_rule(self, rule_id: str, **fields: Any) -> NotificationRule:
        with session_scope(write=True) as s:
            rule = s.get(NotificationRule, rule_id)
            assert rule is not None
            for k, v in fields.items():
                setattr(rule, k, v)
            s.flush()
            return rule

    def delete_rule(self, user_id: str, rule_id: str) -> bool:
        with session_scope(write=True) as s:
            rule = s.get(NotificationRule, rule_id)
            if rule is None or rule.user_id != user_id:
                return False
            s.delete(rule)
            return True

    # ------------------------------------------------------------- deliveries
    def add_delivery(self, user_id: str, **fields: Any) -> NotificationDelivery:
        with session_scope(write=True) as s:
            d = NotificationDelivery(user_id=user_id, **fields)
            s.add(d)
            s.flush()
            return d

    def list_deliveries(self, user_id: str, limit: int = 50) -> list[NotificationDelivery]:
        with session_scope() as s:
            q = (
                select(NotificationDelivery)
                .where(NotificationDelivery.user_id == user_id)
                .order_by(NotificationDelivery.created_at.desc())
                .limit(limit)
            )
            return list(s.scalars(q))

    # --------------------------------------------------------------- projects
    def add_project(self, user_id: str, **fields: Any) -> Project:
        with session_scope(write=True) as s:
            p = Project(user_id=user_id, **fields)
            s.add(p)
            s.flush()
            return p

    def get_project(self, user_id: str, project_id: str) -> Project | None:
        with session_scope() as s:
            p = s.get(Project, project_id)
            return p if p is not None and p.user_id == user_id else None

    def list_projects(self, user_id: str) -> list[Project]:
        with session_scope() as s:
            return list(s.scalars(select(Project).where(Project.user_id == user_id).order_by(Project.created_at)))

    def update_project(self, project_id: str, **fields: Any) -> Project:
        with session_scope(write=True) as s:
            p = s.get(Project, project_id)
            assert p is not None
            for k, v in fields.items():
                setattr(p, k, v)
            s.flush()
            return p

    def delete_project(self, user_id: str, project_id: str) -> bool:
        with session_scope(write=True) as s:
            p = s.get(Project, project_id)
            if p is None or p.user_id != user_id:
                return False
            watch_ids = select(Watch.id).where(Watch.project_id == project_id)
            s.execute(delete(WatchReport).where(WatchReport.watch_id.in_(watch_ids)))
            s.execute(delete(Watch).where(Watch.project_id == project_id))
            s.execute(delete(ProjectFile).where(ProjectFile.project_id == project_id))
            s.delete(p)
            return True

    def replace_project_files(self, project_id: str, files: list[dict[str, Any]]) -> None:
        with session_scope(write=True) as s:
            s.execute(delete(ProjectFile).where(ProjectFile.project_id == project_id))
            for f in files:
                s.add(ProjectFile(project_id=project_id, **f))

    def upsert_project_files(self, project_id: str, files: list[dict[str, Any]]) -> None:
        with session_scope(write=True) as s:
            for f in files:
                existing = s.scalars(select(ProjectFile).where(ProjectFile.project_id == project_id, ProjectFile.path == f["path"])).first()
                if existing is None:
                    s.add(ProjectFile(project_id=project_id, **f))
                else:
                    for k, v in f.items():
                        setattr(existing, k, v)

    def delete_project_file(self, project_id: str, path: str) -> bool:
        with session_scope(write=True) as s:
            res = s.execute(delete(ProjectFile).where(ProjectFile.project_id == project_id, ProjectFile.path == path))
            return bool(res.rowcount)

    def list_project_files(self, project_id: str) -> list[ProjectFile]:
        with session_scope() as s:
            return list(s.scalars(select(ProjectFile).where(ProjectFile.project_id == project_id).order_by(ProjectFile.path)))

    def project_file_stats(self, project_id: str) -> tuple[int, int]:
        with session_scope() as s:
            row = s.execute(
                select(func.count(ProjectFile.id), func.coalesce(func.sum(ProjectFile.size), 0)).where(ProjectFile.project_id == project_id)
            ).one()
            return int(row[0]), int(row[1])

    # ---------------------------------------------------------------- watches
    def add_watch(self, user_id: str, **fields: Any) -> Watch:
        with session_scope(write=True) as s:
            w = Watch(user_id=user_id, **fields)
            s.add(w)
            s.flush()
            return w

    def get_watch(self, user_id: str | None, watch_id: str) -> Watch | None:
        with session_scope() as s:
            w = s.get(Watch, watch_id)
            if w is None or (user_id is not None and w.user_id != user_id):
                return None
            return w

    def list_watches(self, user_id: str, project_id: str | None = None) -> list[Watch]:
        with session_scope() as s:
            q = select(Watch).where(Watch.user_id == user_id)
            if project_id:
                q = q.where(Watch.project_id == project_id)
            return list(s.scalars(q.order_by(Watch.created_at)))

    def update_watch(self, watch_id: str, **fields: Any) -> Watch:
        with session_scope(write=True) as s:
            w = s.get(Watch, watch_id)
            assert w is not None
            for k, v in fields.items():
                setattr(w, k, v)
            s.flush()
            return w

    def delete_watch(self, user_id: str, watch_id: str) -> bool:
        with session_scope(write=True) as s:
            w = s.get(Watch, watch_id)
            if w is None or w.user_id != user_id:
                return False
            s.execute(delete(WatchReport).where(WatchReport.watch_id == watch_id))
            s.delete(w)
            return True

    def due_watches(self, now: datetime, limit: int = 20) -> list[Watch]:
        with session_scope() as s:
            q = (
                select(Watch)
                .where(Watch.enabled.is_(True), Watch.frequency != "manual", Watch.status != "checking")
                .where(or_(Watch.next_check_at.is_(None), Watch.next_check_at <= now))
                .order_by(Watch.next_check_at)
                .limit(limit)
            )
            return list(s.scalars(q))

    def reset_stuck_watches(self) -> int:
        with session_scope(write=True) as s:
            res = s.execute(update(Watch).where(Watch.status == "checking").values(status="pending"))
            return int(res.rowcount or 0)

    # ---------------------------------------------------------------- reports
    def add_report(self, **fields: Any) -> WatchReport:
        with session_scope(write=True) as s:
            r = WatchReport(**fields)
            s.add(r)
            s.flush()
            return r

    def get_report(self, user_id: str, report_id: str) -> WatchReport | None:
        with session_scope() as s:
            r = s.get(WatchReport, report_id)
            return r if r is not None and r.user_id == user_id else None

    def list_reports(self, user_id: str, watch_id: str, limit: int = 30) -> list[WatchReport]:
        with session_scope() as s:
            q = (
                select(WatchReport)
                .where(WatchReport.user_id == user_id, WatchReport.watch_id == watch_id)
                .order_by(WatchReport.created_at.desc())
                .limit(limit)
            )
            return list(s.scalars(q))

    def latest_report(self, watch_id: str) -> WatchReport | None:
        with session_scope() as s:
            return s.scalars(
                select(WatchReport).where(WatchReport.watch_id == watch_id).order_by(WatchReport.created_at.desc()).limit(1)
            ).first()
