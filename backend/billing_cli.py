"""Owner's console for the manual payment flow — until there is an admin panel.

    python -m backend.billing_cli pending                 what is waiting
    python -m backend.billing_cli approve 7               credit + unlock premium
    python -m backend.billing_cli reject 7 -n "no match"  refuse, with a reason
    python -m backend.billing_cli grant sam@x.com 50000   gift or refund credits
    python -m backend.billing_cli grant sam@x.com -5000   claw back
    python -m backend.billing_cli premium sam@x.com on    flip the flag by hand
    python -m backend.billing_cli show sam@x.com          balance + recent ledger

Run from the repo root (or inside the container: `docker exec <ctr> python -m
backend.billing_cli ...`). Talks to whatever DATABASE_URL points at.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from backend import credits
from backend.db import SessionLocal, init_db
from backend.models import CreditEntry, PaymentRequest, User


def _user(db, email: str) -> User:
    user = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None:
        sys.exit(f"No account with email {email!r}")
    return user


def _payment(db, payment_id: int) -> PaymentRequest:
    request = db.get(PaymentRequest, payment_id)
    if request is None:
        sys.exit(f"No payment request #{payment_id}")
    return request


def cmd_pending(args) -> None:
    query = (
        select(PaymentRequest, User.email)
        .join(User, User.id == PaymentRequest.user_id)
        .order_by(PaymentRequest.id)
    )
    if not args.all:
        query = query.where(PaymentRequest.status == "pending")
    with SessionLocal() as db:
        rows = db.execute(query).all()
    if not rows:
        print("Nothing pending.")
        return
    # Plain ASCII throughout: a Windows console defaults to cp1252 and
    # would choke on a rupee sign.
    print(f"{'id':>4}  {'status':<9} {'inr':>4}  {'credits':>8}  {'reference':<24} {'email':<30} note")
    for request, email in rows:
        print(
            f"{request.id:>4}  {request.status:<9} {request.amount_inr:>4}  {request.credits:>8}  "
            f"{request.reference:<24} {email:<30} {request.note}"
        )


def cmd_approve(args) -> None:
    with SessionLocal() as db:
        request = _payment(db, args.id)
        try:
            entry = credits.approve_payment(db, request, args.note or "approved via cli")
        except ValueError as exc:
            sys.exit(str(exc))
        user = db.get(User, request.user_id)
    print(
        f"Approved #{request.id}: +{request.credits} credits -> {user.email} "
        f"(balance {entry.balance_after}, premium on)"
    )


def cmd_reject(args) -> None:
    with SessionLocal() as db:
        request = _payment(db, args.id)
        try:
            credits.reject_payment(db, request, args.note or "rejected via cli")
        except ValueError as exc:
            sys.exit(str(exc))
    print(f"Rejected #{request.id} ({request.reference}).")


def cmd_grant(args) -> None:
    with SessionLocal() as db:
        user = _user(db, args.email)
        try:
            entry = credits.adjust(db, user, args.delta, args.note or "adjustment via cli")
        except ValueError as exc:
            sys.exit(str(exc))
    sign = "+" if args.delta > 0 else ""
    print(f"{sign}{args.delta} credits -> {user.email} (balance {entry.balance_after})")


def cmd_premium(args) -> None:
    with SessionLocal() as db:
        user = _user(db, args.email)
        user.is_premium = args.state == "on"
        if user.is_premium and user.premium_since is None:
            from backend.db import utcnow

            user.premium_since = utcnow()
        db.commit()
    print(f"premium {'on' if user.is_premium else 'off'} -> {user.email}")


def cmd_show(args) -> None:
    with SessionLocal() as db:
        user = _user(db, args.email)
        rows = (
            db.execute(
                select(CreditEntry)
                .where(CreditEntry.user_id == user.id)
                .order_by(CreditEntry.id.desc())
                .limit(args.limit)
            )
            .scalars()
            .all()
        )
    print(f"{user.email}  balance={user.credit_balance}  premium={'yes' if user.is_premium else 'no'}")
    for row in rows:
        what = f"{row.provider}/{row.model} {row.prompt_tokens}+{row.completion_tokens}tok" if row.kind == "usage" else row.note
        flag = " (est)" if row.estimated else ""
        print(f"  #{row.id:<6} {row.kind:<10} {row.delta:>+8}  = {row.balance_after:>8}  {what}{flag}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="billing_cli", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pending", help="list payment requests waiting for review")
    p.add_argument("--all", action="store_true", help="include approved and rejected")
    p.set_defaults(run=cmd_pending)

    p = sub.add_parser("approve", help="credit the pack and unlock premium")
    p.add_argument("id", type=int)
    p.add_argument("-n", "--note", default="")
    p.set_defaults(run=cmd_approve)

    p = sub.add_parser("reject", help="refuse a payment request")
    p.add_argument("id", type=int)
    p.add_argument("-n", "--note", default="")
    p.set_defaults(run=cmd_reject)

    p = sub.add_parser("grant", help="add (or with a negative number, remove) credits")
    p.add_argument("email")
    p.add_argument("delta", type=int)
    p.add_argument("-n", "--note", default="")
    p.set_defaults(run=cmd_grant)

    p = sub.add_parser("premium", help="set the premium flag directly")
    p.add_argument("email")
    p.add_argument("state", choices=["on", "off"])
    p.set_defaults(run=cmd_premium)

    p = sub.add_parser("show", help="balance and recent ledger for an account")
    p.add_argument("email")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(run=cmd_show)

    args = parser.parse_args(argv)
    init_db()
    args.run(args)


if __name__ == "__main__":
    main()
