"""Request bodies for accounts, notifications, projects and watches."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChannelCreate(_Strict):
    kind: Literal["email", "slack", "discord", "webhook"]
    name: str = Field(default="", max_length=120)
    target: str = Field(min_length=3, max_length=2000, description="email address or webhook URL")
    events: list[str] | None = Field(
        default=None, max_length=20, description="events this channel should receive; defaults to the usual set"
    )


class ChannelUpdate(_Strict):
    name: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    events: list[str] | None = Field(default=None, max_length=20)


class ChannelVerify(_Strict):
    code: str = Field(min_length=4, max_length=12)


class RuleCreate(_Strict):
    event: str = Field(max_length=64)
    channel_ids: list[str] = Field(default_factory=list, max_length=25)
    filters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RuleUpdate(_Strict):
    channel_ids: list[str] | None = Field(default=None, max_length=25)
    filters: dict[str, Any] | None = None
    enabled: bool | None = None


class ProjectFileIn(_Strict):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=400_000)


class ProjectCreate(_Strict):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=8000)
    source: Literal["github", "upload"] = "upload"
    repository_url: str | None = Field(default=None, max_length=300)
    branch: str = Field(default="main", max_length=200)
    files: list[ProjectFileIn] = Field(default_factory=list, max_length=400)


class ProjectUpdate(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=8000)
    repository_url: str | None = Field(default=None, max_length=300)
    branch: str | None = Field(default=None, max_length=200)


class ProjectFilesPut(_Strict):
    files: list[ProjectFileIn] = Field(max_length=400)
    replace: bool = False


class WatchCreate(_Strict):
    upstream_url: str = Field(max_length=300)
    branch: str | None = Field(default=None, max_length=200)
    package_name: str | None = Field(default=None, max_length=214)
    import_names: list[str] = Field(default_factory=list, max_length=10)
    ecosystem: Literal["PyPI", "npm"] | None = None
    frequency: Literal["hourly", "daily", "weekly", "manual"] = "daily"
    check_now: bool = True


class WatchUpdate(_Strict):
    branch: str | None = Field(default=None, max_length=200)
    package_name: str | None = Field(default=None, max_length=214)
    import_names: list[str] | None = Field(default=None, max_length=10)
    frequency: Literal["hourly", "daily", "weekly", "manual"] | None = None
    enabled: bool | None = None
