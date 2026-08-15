"""Data access for threads and their memory.

The routers in `conversations.py` and `chat.py` both go through here, which
keeps the ownership check — "does this thread belong to the caller?" — in one
place rather than repeated at every endpoint.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import DEFAULT_SYSTEM_PROMPT, MEMORY_WINDOW_MESSAGES
from backend.models import Conversation, Message, User
from backend.providers import ChatMessage
from backend.schemas import ConversationDetail, ConversationOut, MessageOut


def owned_conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    """Fetch a thread, or 404.

    Somebody else's thread reports 404 rather than 403 on purpose: a 403 would
    confirm that the id exists.
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such conversation")
    return conversation


def summarise(conversation: Conversation, message_count: int) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title or "New thread",
        provider=conversation.provider,
        model=conversation.model,
        message_count=message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def count_messages(db: Session, conversation_id: str) -> int:
    return int(
        db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        ).scalar_one()
    )


def list_summaries(db: Session, user: User) -> list[ConversationOut]:
    """The sidebar, newest thread first — one query, counts included."""
    activity = (
        select(
            Message.conversation_id.label("cid"),
            func.count(Message.id).label("n"),
            func.max(Message.id).label("last_id"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(Conversation, func.coalesce(activity.c.n, 0))
        .outerjoin(activity, activity.c.cid == Conversation.id)
        .where(Conversation.user_id == user.id)
        # Two threads touched inside the same clock tick carry the same
        # `updated_at`, and SQL leaves a tie in whatever order it likes. Message
        # ids are a strictly increasing sequence, so the newest one breaks the
        # tie the way a reader would expect.
        .order_by(
            Conversation.updated_at.desc(),
            func.coalesce(activity.c.last_id, 0).desc(),
        )
    ).all()
    return [summarise(conversation, count) for conversation, count in rows]


def detail(db: Session, conversation: Conversation) -> ConversationDetail:
    messages = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.id)
        )
        .scalars()
        .all()
    )
    return ConversationDetail(
        **summarise(conversation, len(messages)).model_dump(),
        system_prompt=conversation.system_prompt,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


def title_from(text: str) -> str:
    """Cheap, deterministic thread title: the opening line, trimmed.

    An LLM could write a better one, but it would cost a second round-trip on
    every first message — this is renameable, so it is not worth it.
    """
    line = " ".join(text.split())
    if not line:
        return "New thread"
    if len(line) <= 48:
        return line
    return line[:48].rsplit(" ", 1)[0] + "…"


def memory(db: Session, conversation: Conversation) -> list[ChatMessage]:
    """What the model gets to see: the tail of the stored thread.

    Two deliberate filters — failed turns are skipped so a provider outage does
    not become part of the conversation, and only the newest
    MEMORY_WINDOW_MESSAGES rows are replayed so a long thread cannot outgrow
    the model's context window.
    """
    rows = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.failed.is_(False))
            .order_by(Message.id.desc())
            .limit(MEMORY_WINDOW_MESSAGES)
        )
        .scalars()
        .all()
    )

    turns = [ChatMessage(role=row.role, content=row.content) for row in reversed(rows)]

    system = (conversation.system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
    if system:
        turns.insert(0, ChatMessage(role="system", content=system))
    return turns
