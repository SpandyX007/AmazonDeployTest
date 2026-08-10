"""The four tables behind accounts and per-user chat memory.

    User ──< AuthSession        one row per signed-in browser
     └───< Conversation ──< Message      the thread, and its memory

Everything below hangs off `user_id`, which is what makes one person's threads
invisible to everyone else: queries are always filtered by the account resolved
from the session cookie, never by an id the client supplies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base, as_utc, utcnow


def _uuid() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    #: Stored lowercased so "Sam@x.com" and "sam@x.com" are one account.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        if not parts:
            return self.email[:1].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[-1][:1]).upper()


class AuthSession(Base):
    """One signed-in browser.

    The cookie carries a random token; only its SHA-256 is stored here, so a
    database leak yields no usable sessions. Rows are kept (rather than issuing
    self-contained JWTs) precisely so that logout can *revoke* — a token stops
    working the instant this row is marked, not whenever it happens to expire.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Context for the "signed-in devices" list — never used for authorisation.
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")

    user: Mapped[User] = relationship(back_populates="sessions")

    def is_live(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        expires = as_utc(self.expires_at)
        return self.revoked_at is None and expires is not None and expires > now


class Conversation(Base):
    """A thread. Its `Message` rows *are* the memory — the client never posts
    history back, so what the model sees is always what the server stored."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="")
    #: Last provider/model used here, so reopening a thread restores the pick.
    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    #: Per-thread system prompt; falls back to config.DEFAULT_SYSTEM_PROMPT.
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    """One turn.

    The primary key is a plain autoincrementing integer because replay order is
    the whole point: two turns can land in the same microsecond, so sorting by
    timestamp is not reliable enough to rebuild a conversation from.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    #: Byline stamped on assistant turns, so a thread that switched models
    #: still shows which mind said what.
    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    #: A turn that errored. Kept for the UI, skipped when rebuilding memory —
    #: a provider outage should not become part of the conversation.
    failed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
