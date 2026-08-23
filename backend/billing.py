"""Balance, history, and the hand-verified UPI top-up.

No payment gateway. The flow is the one every small shop in India runs:

    1. GET  /api/billing/me        what do I have, what is on sale, where do I pay
    2.      /api/billing/qr.svg    the owner's UPI QR (scan it, pay ₹N)
    3. POST /api/billing/payments  "paid — here is the transaction reference"
    4.      the owner checks the reference against their bank and runs
            `python -m backend.billing_cli approve <id>`, which credits the
            pack and unlocks premium.

Until step 4 the request sits as `pending`, and the UI says so. Nothing in
this file can unlock anything on its own — that is the whole point of a
manual flow, and also its cost: the owner is the webhook.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.config import (
    BACKEND_DIR,
    FREE_SIGNUP_CREDITS,
    PAID_PACK_CREDITS,
    PAID_PACK_PRICE_INR,
    UPI_ID,
    UPI_PAYEE_NAME,
    UPI_QR_IMAGE,
)
from backend.credits import pending_payment, submit_payment
from backend.db import get_db
from backend.models import CreditEntry, PaymentRequest, User
from backend.schemas import (
    BillingOut,
    CreditEntryOut,
    PackOut,
    PaymentOut,
    PaymentSubmitRequest,
    UpiOut,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])

QR_PATH = "/api/billing/qr.svg"


# --- UPI -------------------------------------------------------------------


def upi_uri() -> str:
    """The `upi://pay` deep link every UPI app understands.

    `tn` (the note) shows up on the owner's statement next to the credit, which
    is what makes matching a reference to a payment a ten-second job.
    """
    params = {
        "pa": UPI_ID,
        "pn": UPI_PAYEE_NAME or UPI_ID.split("@")[0],
        "am": f"{PAID_PACK_PRICE_INR}.00",
        "cu": "INR",
        "tn": f"Nexus credits {PAID_PACK_CREDITS}",
    }
    return "upi://pay?" + "&".join(f"{key}={quote(value, safe='')}" for key, value in params.items())


def _upi() -> UpiOut | None:
    if not UPI_ID:
        return None
    return UpiOut(
        id=UPI_ID,
        payee_name=UPI_PAYEE_NAME or UPI_ID.split("@")[0],
        uri=upi_uri(),
        qr_url=QR_PATH,
    )


def _render_qr_svg(data: str) -> bytes:
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(
        data,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=12,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    return image.to_string()


_MEDIA = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@router.get("/qr.svg", include_in_schema=False)
def qr_image():
    """The QR to scan. Public, since an `<img>` tag cannot carry a bearer
    token — and a payment QR is the one thing meant to be shown around."""
    if UPI_QR_IMAGE:
        path = Path(UPI_QR_IMAGE)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        if path.is_file():
            media = _MEDIA.get(path.suffix.lower(), "application/octet-stream")
            return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=3600"})

    if not UPI_ID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payments are not set up")

    return Response(
        _render_qr_svg(upi_uri()),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# --- account ---------------------------------------------------------------


@router.get("/me", response_model=BillingOut)
def my_billing(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pending = pending_payment(db, user)
    return BillingOut(
        balance=user.credit_balance,
        is_premium=user.is_premium,
        free_signup_credits=FREE_SIGNUP_CREDITS,
        pack=PackOut(price_inr=PAID_PACK_PRICE_INR, credits=PAID_PACK_CREDITS),
        upi=_upi(),
        pending_payment=PaymentOut.model_validate(pending) if pending else None,
    )


@router.get("/history", response_model=list[CreditEntryOut])
def my_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Newest first — the statement behind the number in the sidebar."""
    rows = (
        db.execute(
            select(CreditEntry)
            .where(CreditEntry.user_id == user.id)
            .order_by(CreditEntry.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [CreditEntryOut.model_validate(row) for row in rows]


# --- payments --------------------------------------------------------------


@router.get("/payments", response_model=list[PaymentOut])
def my_payments(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(PaymentRequest)
            .where(PaymentRequest.user_id == user.id)
            .order_by(PaymentRequest.id.desc())
        )
        .scalars()
        .all()
    )
    return [PaymentOut.model_validate(row) for row in rows]


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def claim_payment(
    payload: PaymentSubmitRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Record "I paid". Grants nothing by itself — see the module docstring."""
    request = submit_payment(db, user, payload.reference, payload.note)
    return PaymentOut.model_validate(request)
