"""Ask a case: per-user question threads on an investigation, answered by the responsible agent."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.access import account_rate_limit
from app.api.auth import require_user
from app.api.routes import _get
from app.chat import TOPICS, ChatService
from app.chat.service import MAX_MESSAGES_PER_THREAD, MAX_QUESTION_CHARS
from app.models import User

router = APIRouter(prefix="/api")


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=MAX_QUESTION_CHARS)
    agent: str | None = Field(default=None, max_length=64)


def _chat(request: Request) -> ChatService:
    return request.app.state.chat


@router.get("/chat/agents")
def chat_agents() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "display_name": t.display_name, "category": t.category, "examples": list(t.follow_ups)} for t in TOPICS.values()
    ]


@router.get("/investigations/{investigation_id}/chat")
def history(investigation_id: str, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    _get(request, investigation_id)
    return {"messages": _chat(request).history(investigation_id, user.id)}


@router.post("/investigations/{investigation_id}/chat", dependencies=[Depends(account_rate_limit)])
def ask(investigation_id: str, body: AskBody, request: Request, user: User = Depends(require_user)) -> dict[str, Any]:
    _get(request, investigation_id)
    chat = _chat(request)
    if chat.thread_size(investigation_id, user.id) >= MAX_MESSAGES_PER_THREAD:
        raise HTTPException(status_code=409, detail="This conversation is full. Clear it to start a new one.")
    try:
        return chat.ask(investigation_id, user.id, body.question, agent=body.agent)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="investigation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/investigations/{investigation_id}/chat", status_code=204)
def clear(investigation_id: str, request: Request, user: User = Depends(require_user)) -> Response:
    _get(request, investigation_id)
    _chat(request).clear(investigation_id, user.id)
    return Response(status_code=204)
