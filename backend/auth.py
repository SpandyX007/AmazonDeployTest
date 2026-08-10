"""Accounts and sessions.

The whole mechanism in three lines:

  login    -> verify password, insert an AuthSession row, Set-Cookie the token
  request  -> `current_user` hashes the cookie, looks the row up, returns a User
  logout   -> stamp `revoked_at`, clear the cookie

The cookie is httpOnly, so page JavaScript (including anything injected by an
XSS) cannot read it; and because sessions are rows rather than self-contained
tokens, signing out actually invalidates them server-side.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_MAX_ATTEMPTS_PER_IP,
    MAX_SESSIONS_PER_USER,
    SESSION_COOKIE,
    SESSION_RENEW_AFTER,
    SESSION_TTL_DAYS,
)
from backend.db import as_utc, get_db, utcnow
from backend.models import AuthSession, User
from backend.schemas import LoginRequest, SessionOut, SignupRequest, UserOut
from backend.security import (
    burn_password_time,
    hash_password,
    hash_token,
    login_throttle,
    new_session_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_TTL = timedelta(days=SESSION_TTL_DAYS)


# --- cookie plumbing -------------------------------------------------------


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "path": "/",
    }


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), **_cookie_options()
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, **_cookie_options())


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


def _unauthorised() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue")


# --- session lifecycle -----------------------------------------------------


def _prune(db: Session, user_id: str) -> None:
    """Drop dead sessions, then cap how many browsers stay signed in at once."""
    rows = (
        db.execute(select(AuthSession).where(AuthSession.user_id == user_id))
        .scalars()
        .all()
    )
    now = utcnow()
    live = sorted(
        (r for r in rows if r.is_live(now)),
        key=lambda r: as_utc(r.created_at),
        reverse=True,
    )
    for row in rows:
        if not row.is_live(now) or row in live[MAX_SESSIONS_PER_USER:]:
            db.delete(row)
    db.commit()


def _issue(db: Session, user: User, request: Request, response: Response) -> AuthSession:
    token = new_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + SESSION_TTL,
        user_agent=request.headers.get("user-agent", "")[:300],
        ip=_client_ip(request),
    )
    user.last_login_at = utcnow()
    db.add(session)
    db.commit()

    _prune(db, user.id)
    _set_cookie(response, token)
    return session


def current_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSession:
    """Resolve the session cookie, or 401.

    Also slides the expiry: someone who uses the app daily is never signed out,
    while a session left idle past its TTL still dies on its own.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthorised()

    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).scalar_one_or_none()

    now = utcnow()
    if session is None or not session.is_live(now):
        _clear_cookie(response)
        raise _unauthorised()

    session.last_seen_at = now
    if as_utc(session.expires_at) - now < SESSION_TTL * (1 - SESSION_RENEW_AFTER):
        session.expires_at = now + SESSION_TTL
        _set_cookie(response, token)  # refresh the browser's copy too
    db.commit()

    return session


def current_user(session: AuthSession = Depends(current_session)) -> User:
    """The dependency every protected route uses. Anything reachable from here
    is scoped to one account — routes never trust a user id from the client."""
    return session.user


# --- routes ----------------------------------------------------------------


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()

    user = User(
        email=email,
        name=payload.name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Also catches two simultaneous signups racing on the same address.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")

    _issue(db, user, request, response)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()
    limits = {
        f"email:{email}": LOGIN_MAX_ATTEMPTS,
        f"ip:{_client_ip(request)}": LOGIN_MAX_ATTEMPTS_PER_IP,
    }

    wait = login_throttle.retry_after(limits)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in {max(wait // 60, 1)} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        # Same cost as a real check, so response time reveals nothing about
        # whether the address is registered.
        burn_password_time()
        login_throttle.record_failure(*limits)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")

    if not verify_password(payload.password, user.password_hash):
        login_throttle.record_failure(*limits)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")

    login_throttle.clear(*limits)
    _issue(db, user, request, response)
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    """Called once on boot: the only way the SPA can learn whether the cookie
    it cannot read is still good."""
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: AuthSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    session.revoked_at = utcnow()
    db.commit()
    _clear_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    response: Response,
    session: AuthSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    """Sign out of every browser — the reason sessions are rows and not JWTs."""
    now = utcnow()
    rows = (
        db.execute(select(AuthSession).where(AuthSession.user_id == session.user_id))
        .scalars()
        .all()
    )
    for row in rows:
        row.revoked_at = row.revoked_at or now
    db.commit()
    _clear_cookie(response)


@router.get("/sessions", response_model=list[SessionOut])
def sessions(
    session: AuthSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    now: datetime = utcnow()
    rows = (
        db.execute(
            select(AuthSession)
            .where(AuthSession.user_id == session.user_id)
            .order_by(AuthSession.last_seen_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        SessionOut(
            id=row.id,
            current=row.id == session.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip=row.ip,
        )
        for row in rows
        if row.is_live(now)
    ]
