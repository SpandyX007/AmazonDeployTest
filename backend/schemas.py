"""The wire contract, in one file.

Every model inherits `Schema`, which flips field names to camelCase on the way
out (`created_at` -> `createdAt`) so Python stays snake_case and TypeScript
stays idiomatic without either side translating by hand.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel


def _utc_iso(value: datetime) -> str:
    """Always emit an explicit UTC instant.

    `timestamptz` columns come back aware, but a naive value from anywhere else
    would be read by `new Date("2026-08-10T12:00:00")` in a browser as *local*
    time — so the trailing Z is pinned on here whatever came in.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcTime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str, when_used="json")]


class Schema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# --- auth ------------------------------------------------------------------


class SignupRequest(Schema):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    #: Length is the only rule worth enforcing — composition rules push people
    #: towards "Passw0rd!" and away from long passphrases.
    password: str = Field(min_length=8, max_length=200)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("Name cannot be blank")
        return name


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(Schema):
    id: str
    name: str
    email: str
    #: Derived on the model — the avatar badge in the UI.
    initials: str
    created_at: UtcTime
    #: Snapshot at the time of the call; `done` events carry fresher values.
    credit_balance: int = 0
    is_premium: bool = False


class TokenResponse(Schema):
    """What sign-up, sign-in, and refresh all return.

    The access token is in the body rather than a cookie because a bearer token
    is meant to be attached deliberately, by the caller, on the requests that
    need it — a cookie would be attached automatically to every request the
    browser makes to this origin, which is how CSRF happens.
    """

    access_token: str
    token_type: str = "Bearer"
    #: Seconds until the access token dies. The client refreshes just before.
    expires_in: int
    user: UserOut


class SessionOut(Schema):
    """One signed-in browser, for the "where am I logged in" list.

    The id is the refresh *family* — a session is a chain of rotated tokens, so
    the family is the only id that stays stable across refreshes.
    """

    id: str
    #: True for the session that made this request.
    current: bool
    started_at: UtcTime
    refreshed_at: UtcTime
    expires_at: UtcTime
    user_agent: str
    ip: str


# --- conversations ---------------------------------------------------------


class MessageOut(Schema):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    provider: str
    model: str
    failed: bool
    created_at: UtcTime

    @field_validator("id", mode="before")
    @classmethod
    def _as_text(cls, value: object) -> str:
        # Rows use an autoincrementing integer key; the wire keeps ids opaque.
        return str(value)


class ConversationOut(Schema):
    id: str
    title: str
    provider: str
    model: str
    message_count: int
    created_at: UtcTime
    updated_at: UtcTime


class ConversationDetail(ConversationOut):
    system_prompt: str
    messages: list[MessageOut]


class RenameRequest(Schema):
    title: str = Field(min_length=1, max_length=120)


# --- chat ------------------------------------------------------------------


class ChatTurnRequest(Schema):
    """One turn.

    Note what is *absent*: the conversation history. The client sends only the
    new message and which thread it belongs to; the server replays memory from
    its own rows, so a tampered-with client cannot rewrite what was said.
    """

    provider: str
    model: str
    content: str = ""
    #: Omit to start a new thread — the response's `meta` event carries the id.
    conversation_id: str | None = None
    #: Sets the thread's system prompt (persisted) when provided.
    system: str | None = None
    #: Id of an assistant message to redo. That message and everything after it
    #: are deleted, then the question before it is asked again — which is what
    #: makes retrying a turn from the middle of a thread coherent rather than
    #: leaving orphaned replies behind it.
    regenerate_from: str | None = None

    @model_validator(mode="after")
    def _coherent(self) -> ChatTurnRequest:
        if not self.regenerate_from and not self.content.strip():
            raise ValueError("A message is required")
        if self.regenerate_from and not self.conversation_id:
            raise ValueError("Regenerating needs a conversation")
        return self


class TurnUsage(Schema):
    """What one turn cost, as reported back on `done` and in `ChatReply`."""

    prompt_tokens: int
    completion_tokens: int
    #: True when the vendor sent no count and the numbers are ours.
    estimated: bool
    credits_charged: int
    #: The balance after the charge — the client updates its meter from this
    #: rather than re-fetching.
    balance: int


class ChatReply(Schema):
    conversation_id: str
    title: str
    message: MessageOut
    usage: TurnUsage | None = None


# --- billing ---------------------------------------------------------------


class PackOut(Schema):
    """The one thing on sale."""

    price_inr: int
    credits: int


class UpiOut(Schema):
    id: str
    payee_name: str
    #: `upi://pay?...` — opens the payer's UPI app directly on a phone.
    uri: str
    #: Where to fetch the QR image from.
    qr_url: str


class PaymentOut(Schema):
    id: int
    amount_inr: int
    credits: int
    reference: str
    note: str
    status: Literal["pending", "approved", "rejected"]
    created_at: UtcTime
    resolved_at: UtcTime | None
    resolution_note: str


class BillingOut(Schema):
    """Everything the paywall and the credit meter need, in one call."""

    balance: int
    is_premium: bool
    free_signup_credits: int
    pack: PackOut
    #: Absent when the owner has not configured UPI_ID — the UI then says
    #: "not available" instead of showing an empty QR.
    upi: UpiOut | None
    pending_payment: PaymentOut | None


class CreditEntryOut(Schema):
    id: int
    kind: Literal["signup", "usage", "payment", "adjustment"]
    delta: int
    balance_after: int
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated: bool
    conversation_id: str | None
    note: str
    created_at: UtcTime


class PaymentSubmitRequest(Schema):
    reference: str = Field(min_length=6, max_length=80)
    note: str = Field(default="", max_length=200)
