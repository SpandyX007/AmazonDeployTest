"""Accounts and JWT sessions.

Two credentials, with different jobs.

  access token   a signed JWT, ~15 minutes, sent as `Authorization: Bearer`.
                 Verified by maths alone — no database read — which is what
                 makes it fast, and also what makes it unrevocable. Its short
                 life *is* its safety margin.

  refresh token  an opaque random string in an httpOnly cookie, ~30 days,
                 stored hashed and checked against a row. Its only power is to
                 mint access tokens, and it is revocable, rotated on every use,
                 and scoped by cookie path so it never rides along on ordinary
                 API calls.

The split is the point: the credential that travels constantly is the one that
expires quickly, and the credential that lives a long time barely travels.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_MAX_ATTEMPTS_PER_IP,
    MAX_SESSIONS_PER_USER,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    REFRESH_REUSE_GRACE_SECONDS,
    REFRESH_TOKEN_TTL_DAYS,
)
from backend.credits import grant_signup_credits
from backend.db import as_utc, get_db, utcnow
from backend.models import RefreshToken, User
from backend.schemas import LoginRequest, SessionOut, SignupRequest, TokenResponse, UserOut
from backend.security import (
    burn_password_time,
    hash_password,
    hash_token,
    login_throttle,
    new_refresh_token,
    verify_password,
)
from backend.tokens import InvalidToken, mint_access_token, read_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_TTL = timedelta(days=REFRESH_TOKEN_TTL_DAYS)

#: `auto_error=False` so a missing header reaches our own handler and returns
#: the same shaped error as a bad one, instead of FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /api/auth/login")


# --- errors ----------------------------------------------------------------


def _unauthorised(detail: str, *, expired: bool = False) -> HTTPException:
    """401 with a machine-readable hint.

    `token_expired` tells the client "refresh and retry"; anything else means
    "the session is over, sign in again". Without the distinction the client
    would have to guess, and would either retry pointlessly or sign the user
    out over a token that was merely stale.
    """
    code = "token_expired" if expired else "invalid_token"
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail,
        headers={"WWW-Authenticate": f'Bearer error="{code}"'},
    )


# --- the dependency every protected route uses ------------------------------


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Turn a bearer token into an account.

    Note what is *not* here: any lookup of a session. The signature already
    proves the token was minted by this service and has not been edited, and
    `exp` already proves it is current. The one row we do read is the account
    itself, because a token can outlive the user it names.
    """
    if credentials is None:
        raise _unauthorised("Sign in to continue")

    try:
        user_id = read_access_token(credentials.credentials)
    except InvalidToken as invalid:
        raise _unauthorised(invalid.reason, expired=invalid.expired) from None

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorised("That account no longer exists")

    return user


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """`current_user` for routes that work signed out but do more signed in.

    A bad token is treated as no token: the route answers the anonymous way
    rather than failing, because nothing behind it is private.
    """
    if credentials is None:
        return None
    try:
        return db.get(User, read_access_token(credentials.credentials))
    except InvalidToken:
        return None


# --- refresh cookie plumbing ------------------------------------------------


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        # Scoped to /api/auth: the browser attaches this to refresh and logout
        # and to nothing else, so the long-lived credential is absent from the
        # request that streams a chat turn.
        "path": REFRESH_COOKIE_PATH,
    }


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=int(REFRESH_TTL.total_seconds()), **_cookie_options()
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, **_cookie_options())


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


# --- session lifecycle ------------------------------------------------------


def _revoke_family(db: Session, family_id: str) -> None:
    """Kill an entire chain — used on logout and on replay detection."""
    now = utcnow()
    rows = (
        db.execute(select(RefreshToken).where(RefreshToken.family_id == family_id))
        .scalars()
        .all()
    )
    for row in rows:
        if row.revoked_at is None:
            row.revoked_at = now
    db.commit()


def _prune(db: Session, user_id: str) -> None:
    """Drop spent and expired rungs, then cap concurrent sign-ins."""
    now = utcnow()
    rows = (
        db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
        .scalars()
        .all()
    )

    # A spent rung is only interesting for as long as replaying it should still
    # be treated as an attack; past its own expiry it is just noise.
    for row in rows:
        expires = as_utc(row.expires_at)
        if row.revoked_at is not None or (expires is not None and expires <= now):
            db.delete(row)

    live = sorted(
        (r for r in rows if r.is_live(now)),
        key=lambda r: as_utc(r.family_started_at),
        reverse=True,
    )
    for stale in live[MAX_SESSIONS_PER_USER:]:
        stale.revoked_at = now

    db.commit()


def _issue(
    db: Session,
    user: User,
    request: Request,
    response: Response,
    *,
    family_id: str | None = None,
    family_started_at=None,
) -> TokenResponse:
    """Mint an access/refresh pair.

    Passing a `family_id` continues an existing sign-in (a rotation); omitting
    it starts a new one (a fresh login).
    """
    raw_refresh = new_refresh_token()
    now = utcnow()

    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4().hex,
            family_started_at=family_started_at or now,
            token_hash=hash_token(raw_refresh),
            expires_at=now + REFRESH_TTL,
            user_agent=request.headers.get("user-agent", "")[:300],
            ip=_client_ip(request),
        )
    )
    db.commit()
    _prune(db, user.id)

    _set_refresh_cookie(response, raw_refresh)
    access = mint_access_token(user.id)

    return TokenResponse(
        access_token=access.token,
        expires_in=access.expires_in,
        user=UserOut.model_validate(user),
    )


# --- routes ----------------------------------------------------------------


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
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

    # The free allowance — written as a ledger row, not a column default, so
    # the account's history starts with where its first credits came from.
    grant_signup_credits(db, user)

    return _issue(db, user, request, response)


@router.post("/login", response_model=TokenResponse)
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
    user.last_login_at = utcnow()
    db.commit()

    return _issue(db, user, request, response)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Exchange the refresh cookie for a new access token, and rotate.

    This is also how the app boots: on a page load the SPA has no access token
    in memory (it never persists one), so it calls this and finds out both
    whether it is signed in and as whom.
    """
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise _unauthorised("No session to refresh")

    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
    ).scalar_one_or_none()

    now = utcnow()

    if row is None:
        _clear_refresh_cookie(response)
        raise _unauthorised("That session is not recognised")

    if row.revoked_at is not None:
        _clear_refresh_cookie(response)
        raise _unauthorised("That session was signed out")

    expires = as_utc(row.expires_at)
    if expires is None or expires <= now:
        _clear_refresh_cookie(response)
        raise _unauthorised("That session has expired")

    if row.used_at is not None:
        # This rung was already exchanged. Either two tabs raced each other,
        # or a copy of the token exists somewhere it should not.
        spent_ago = (now - as_utc(row.used_at)).total_seconds()
        if spent_ago > REFRESH_REUSE_GRACE_SECONDS:
            _revoke_family(db, row.family_id)
            _clear_refresh_cookie(response)
            raise _unauthorised("This session was reused elsewhere — please sign in again")
        # Inside the grace window: treat it as the race it almost certainly is
        # and hand out a fresh rung rather than logging an innocent user out.

    user = db.get(User, row.user_id)
    if user is None:
        _clear_refresh_cookie(response)
        raise _unauthorised("That account no longer exists")

    row.used_at = row.used_at or now
    db.commit()

    return _issue(
        db,
        user,
        request,
        response,
        family_id=row.family_id,
        family_started_at=row.family_started_at,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Revoke this browser's chain.

    Driven by the refresh cookie, not by the access token: the cookie is what
    identifies *which* sign-in to end, and it is the half that would otherwise
    outlive the click. Any access token already issued stays technically valid
    until it expires — the client drops it, and it cannot be renewed.
    """
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        row = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        ).scalar_one_or_none()
        if row is not None:
            _revoke_family(db, row.family_id)

    _clear_refresh_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Sign out of every browser — the reason refresh tokens are rows."""
    now = utcnow()
    rows = (
        db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
        .scalars()
        .all()
    )
    for row in rows:
        row.revoked_at = row.revoked_at or now
    db.commit()

    _clear_refresh_cookie(response)


@router.get("/sessions", response_model=list[SessionOut])
def sessions(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Live sign-ins, one row per family.

    Exactly one rung of each chain is unspent at any moment, so "the live rungs"
    and "the live sessions" are the same list.
    """
    raw = request.cookies.get(REFRESH_COOKIE)
    mine = hash_token(raw) if raw else None
    now = utcnow()

    rows = (
        db.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .order_by(RefreshToken.created_at.desc())
        )
        .scalars()
        .all()
    )

    return [
        SessionOut(
            id=row.family_id,
            current=row.token_hash == mine,
            started_at=row.family_started_at,
            refreshed_at=row.created_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip=row.ip,
        )
        for row in rows
        if row.is_live(now)
    ]
