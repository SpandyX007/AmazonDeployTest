"""The tables behind accounts, per-user chat memory, and the credit balance.

    User ──< RefreshToken       the rotating chain behind one sign-in
     ├───< Conversation ──< Message      the thread, and its memory
     ├───< CreditEntry         every movement of the balance, signed
     └───< PaymentRequest      "I paid the QR — here is the reference"

Everything below hangs off `user_id`, which is what makes one person's threads
invisible to everyone else: queries are always filtered by the account resolved
from the session cookie, never by an id the client supplies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false
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

    #: Cached sum of `credit_entries.delta`. The ledger is the truth; this is
    #: what the hot path reads. It may dip below zero: a turn's cost is only
    #: known once it ends, and the last turn of a balance is allowed to finish.
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Unlocks premium-tier models. Flipped by an approved payment.
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    premium_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    credit_entries: Mapped[list[CreditEntry]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payment_requests: Mapped[list[PaymentRequest]] = relationship(
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


class RefreshToken(Base):
    """One rung on a session's ladder.

    Access tokens are JWTs and are never stored — they are believed on sight,
    because the signature is the proof. This table holds the other half: the
    long-lived, *revocable* credential that mints them.

    Two shapes worth noticing.

    It is an opaque random string, not a JWT. A refresh must consult the
    database anyway — is this revoked? was it already spent? — and once you are
    reading a row, a self-validating token buys nothing. Only the SHA-256 is
    stored, so a database leak hands over no working sessions.

    And it rotates. Every refresh spends the current token (`used_at`) and
    issues a successor in the same `family_id`, so one sign-in is a chain, not a
    single long-lived key. If a *spent* token is ever presented again, a copy of
    it exists somewhere it should not — and the whole family is burned.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: Shared by every rung of one sign-in — this is what "a session" means now.
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    #: When the chain began. Copied forward on rotation so the "signed-in
    #: devices" list can show session age without walking back up the chain.
    family_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    #: Set when this rung is exchanged for the next one. A second presentation
    #: after this is set is the replay signal.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Context for the "signed-in devices" list — never used for authorisation.
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def is_live(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        expires = as_utc(self.expires_at)
        return (
            self.revoked_at is None
            and self.used_at is None
            and expires is not None
            and expires > now
        )


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


class CreditEntry(Base):
    """One signed movement of a balance — the ledger.

    Append-only. A mistake is corrected by a new row with the opposite sign,
    never by editing this one, so the history always explains the balance. A
    usage row also records what was bought: which model, how many tokens, and
    whether the count came from the vendor or from our own estimate.
    """

    __tablename__ = "credit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: signup | usage | payment | adjustment
    kind: Mapped[str] = mapped_column(String(16), index=True)
    #: Negative for a charge, positive for a grant.
    delta: Mapped[int] = mapped_column(Integer)
    #: The cached balance right after this row applied — lets the history
    #: screen show a running total without summing from the beginning.
    balance_after: Mapped[int] = mapped_column(Integer)

    # -- usage rows only --
    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    #: The vendor reported nothing and the count is ours.
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), default=None
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), default=None
    )

    # -- payment rows only --
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_requests.id", ondelete="SET NULL"), default=None
    )

    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="credit_entries")


class PaymentRequest(Base):
    """A claim that the QR was paid, waiting for the owner to agree.

    There is no gateway, so nothing here is proof. The user scans the UPI QR,
    pays, and types in the transaction reference their app shows; the owner
    checks that reference against their own bank statement and approves. The
    reference is unique across all users so one screenshot cannot be submitted
    twice, and `credits`/`amount` are copied in at submission time so a later
    price change does not rewrite what was owed.
    """

    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount_inr: Mapped[int] = mapped_column(Integer)
    credits: Mapped[int] = mapped_column(Integer)
    #: UPI transaction id / UTR as the payer's app shows it. Normalised
    #: uppercase, no spaces.
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    #: Anything the payer wants to add — the name on their UPI account, say.
    note: Mapped[str] = mapped_column(String(200), default="")
    #: pending | approved | rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Why it was rejected, or who approved it.
    resolution_note: Mapped[str] = mapped_column(String(200), default="")

    user: Mapped[User] = relationship(back_populates="payment_requests")
