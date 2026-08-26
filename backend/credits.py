"""Everything that moves a credit balance, and the two gates in front of chat.

Three rules keep this honest.

The balance is never read-then-written. Every change is one atomic
`UPDATE users SET credit_balance = credit_balance + :delta ... RETURNING`, so
two turns finishing at the same instant cannot each read 100, each subtract
60, and each write 40. The returned value is what the ledger records.

Every change has a ledger row. `User.credit_balance` is a cache of
`sum(credit_entries.delta)`; when someone disputes a number, the rows explain
it, and a wrong charge is undone by a new row of the opposite sign.

Charging happens *after* the turn, on the turn's real cost. The gate before
the turn only asks "is there anything left?", which means the final turn of a
balance can push it below zero — by at most one capped reply. That overdraw is
the price of not knowing the cost in advance, and it is bounded by
MAX_COMPLETION_TOKENS.
"""

from __future__ import annotations

import re
from dataclasses import replace

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.config import (
    FREE_SIGNUP_CREDITS,
    PAID_PACK_CREDITS,
    PAID_PACK_PRICE_INR,
    UPI_ID,
)
from backend.db import SessionLocal, utcnow
from backend.models import CreditEntry, PaymentRequest, User
from backend.pricing import ModelPolicy
from backend.providers import ChatMessage, ModelInfo, Usage, estimate_usage


# --- the gates -------------------------------------------------------------


def _denied(code: int, reason: str, message: str, **extra) -> HTTPException:
    """A refusal the client can act on.

    `reason` is the machine-readable half: the frontend shows a paywall for
    `insufficient_credits`, an upgrade prompt for `model_locked`, and a plain
    error for anything else — so it must not have to parse prose to decide.
    """
    return HTTPException(code, {"reason": reason, "message": message, **extra})


def authorise_turn(user: User, model: ModelInfo, policy: ModelPolicy) -> None:
    """Raise unless this account may start a turn on this model right now."""
    if policy.premium and not user.is_premium:
        raise _denied(
            status.HTTP_403_FORBIDDEN,
            "model_locked",
            f"{model.name} is a premium model. Unlock premium to use it.",
            model=model.id,
            tier=policy.tier,
        )

    if user.credit_balance <= 0:
        raise _denied(
            status.HTTP_402_PAYMENT_REQUIRED,
            "insufficient_credits",
            "You have used up your credits. Top up to keep chatting.",
            balance=user.credit_balance,
        )


# --- moving the balance ----------------------------------------------------


def _apply(db: Session, user_id: str, delta: int, **fields) -> CreditEntry:
    """Shift a balance by `delta` and write the matching ledger row.

    Atomic at the database: the arithmetic happens in the UPDATE itself, not
    in Python, and the new balance comes back from the same statement's
    RETURNING clause.
    """
    balance = db.execute(
        update(User)
        .where(User.id == user_id)
        .values(credit_balance=User.credit_balance + delta)
        .returning(User.credit_balance)
    ).scalar_one()

    entry = CreditEntry(user_id=user_id, delta=delta, balance_after=balance, **fields)
    db.add(entry)
    return entry


def grant_signup_credits(db: Session, user: User) -> None:
    """The free allowance, recorded as the account's first ledger row."""
    if FREE_SIGNUP_CREDITS <= 0:
        return
    entry = _apply(db, user.id, FREE_SIGNUP_CREDITS, kind="signup", note="Welcome credits")
    db.commit()
    user.credit_balance = entry.balance_after


def finalise_usage(
    turns: list[ChatMessage], text: str, reported: Usage | None
) -> Usage:
    """The usage to bill: the vendor's count, patched where it was silent."""
    if reported is None:
        return estimate_usage(turns, text)
    if reported.prompt_tokens == 0 and turns:
        # Ollama omits the prompt count when the whole prompt came from its
        # cache; it still cost us the context, so fill it in.
        guess = estimate_usage(turns, "")
        return replace(reported, prompt_tokens=guess.prompt_tokens, estimated=True)
    return reported


def charge_usage(
    *,
    user_id: str,
    conversation_id: str | None,
    message_id: int | None,
    provider_id: str,
    model_id: str,
    usage: Usage,
    policy: ModelPolicy,
) -> dict:
    """Debit one finished turn. Opens its own session: the caller is usually a
    streaming body that has outlived the request's session."""
    cost = policy.cost(usage)
    with SessionLocal() as db:
        entry = _apply(
            db,
            user_id,
            -cost,
            kind="usage",
            provider=provider_id,
            model=model_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            estimated=usage.estimated,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        db.commit()
        balance = entry.balance_after

    return {
        "promptTokens": usage.prompt_tokens,
        "completionTokens": usage.completion_tokens,
        "estimated": usage.estimated,
        "creditsCharged": cost,
        "balance": balance,
    }


# --- manual payments -------------------------------------------------------

_REFERENCE = re.compile(r"^[A-Z0-9\-]{6,64}$")


def normalise_reference(raw: str) -> str:
    """UTRs are 12 digits; UPI txn ids are longer alphanumerics. Accept both,
    in one canonical form, so the same receipt cannot be entered twice as
    'abc 123' and 'ABC123'."""
    reference = re.sub(r"\s+", "", raw).upper()
    if not _REFERENCE.match(reference):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Enter the transaction reference (UTR / transaction ID) exactly as your UPI app shows it.",
        )
    return reference


def pending_payment(db: Session, user: User) -> PaymentRequest | None:
    return db.execute(
        select(PaymentRequest)
        .where(PaymentRequest.user_id == user.id, PaymentRequest.status == "pending")
        .order_by(PaymentRequest.created_at.desc())
    ).scalar_one_or_none()


def submit_payment(db: Session, user: User, reference: str, note: str) -> PaymentRequest:
    if not UPI_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are not set up yet")

    if pending_payment(db, user) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have a payment waiting to be verified"
        )

    reference = normalise_reference(reference)
    taken = db.execute(
        select(PaymentRequest.id).where(PaymentRequest.reference == reference)
    ).scalar_one_or_none()
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That transaction has already been submitted")

    request = PaymentRequest(
        user_id=user.id,
        amount_inr=PAID_PACK_PRICE_INR,
        credits=PAID_PACK_CREDITS,
        reference=reference,
        note=" ".join(note.split())[:200],
    )
    db.add(request)
    db.commit()
    return request


def approve_payment(db: Session, request: PaymentRequest, note: str = "") -> CreditEntry:
    """Credit the pack and unlock premium. Idempotent: a second call on an
    already-approved request is a no-op rather than a second grant."""
    if request.status != "pending":
        raise ValueError(f"Payment #{request.id} is already {request.status}")

    now = utcnow()
    request.status = "approved"
    request.resolved_at = now
    request.resolution_note = note[:200]

    entry = _apply(
        db,
        request.user_id,
        request.credits,
        kind="payment",
        payment_id=request.id,
        note=f"INR {request.amount_inr} pack - {request.reference}",
    )

    user = db.get(User, request.user_id)
    if user is not None and not user.is_premium:
        user.is_premium = True
        user.premium_since = now

    db.commit()
    return entry


def reject_payment(db: Session, request: PaymentRequest, note: str = "") -> None:
    if request.status != "pending":
        raise ValueError(f"Payment #{request.id} is already {request.status}")
    request.status = "rejected"
    request.resolved_at = utcnow()
    request.resolution_note = note[:200]
    db.commit()


def adjust(db: Session, user: User, delta: int, note: str) -> CreditEntry:
    """Owner-initiated correction: a refund, a gift, a clawback."""
    if delta == 0:
        raise ValueError("An adjustment of zero changes nothing")
    entry = _apply(db, user.id, delta, kind="adjustment", note=note[:200])
    db.commit()
    user.credit_balance = entry.balance_after
    return entry
