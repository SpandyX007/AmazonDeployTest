"""The JWT layer: minting and verifying access tokens.

Kept apart from `security.py` — which is about passwords — because the two
answer different questions at different rates. "Is this the right password?"
runs once, at sign-in, and is deliberately slow. "Is this token still good?"
runs on every single request and must be fast, which it is: verifying a JWT is
one HMAC over a few hundred bytes, with no database involved at all.

That last property is the whole trade. Nothing is looked up, so nothing can be
revoked — a minted token stays valid until its `exp` passes, full stop. Which
is why `ACCESS_TOKEN_TTL_MINUTES` is small and why the revocable half of the
session lives in `refresh_tokens` instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from backend.config import (
    ACCESS_TOKEN_TTL_MINUTES,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET,
)

ACCESS_TTL = timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)


class InvalidToken(Exception):
    """Missing, malformed, expired, or not issued by us."""

    def __init__(self, reason: str, *, expired: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        #: Lets the API answer "refresh and try again" rather than "sign in".
        self.expired = expired


@dataclass(frozen=True)
class AccessToken:
    token: str
    user_id: str
    expires_at: datetime

    @property
    def expires_in(self) -> int:
        """Seconds of life left, which is what the client is told — an absolute
        timestamp would be read against a clock we do not control."""
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(remaining))


def mint_access_token(user_id: str) -> AccessToken:
    """Sign a token naming one account.

    The claims stay minimal on purpose. A name or email baked in here would go
    stale the moment the user edits it and stay stale until the token expires,
    so the payload carries an id and the response body carries the profile.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + ACCESS_TTL

    claims = {
        "sub": user_id,  # subject — whose token this is
        "iss": JWT_ISSUER,  # issuer — who minted it
        "iat": int(now.timestamp()),  # issued at
        "exp": int(expires_at.timestamp()),  # expires at — enforced on decode
        "jti": uuid.uuid4().hex,  # unique id, for tracing a token through logs
        "typ": "access",
    }

    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return AccessToken(token=token, user_id=user_id, expires_at=expires_at)


def read_access_token(token: str) -> str:
    """Verify a token and return the account id it names."""
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            # Pinning the algorithm list is not optional. Left open, a caller
            # can hand us a token whose own header says `alg: none`, or an
            # HS256 token signed with our *public* key in an RSA setup — the
            # classic JWT confusion attacks. We accept one algorithm: ours.
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            # Reject anything that simply omits the claims we rely on, rather
            # than treating a missing `exp` as "never expires".
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise InvalidToken("Access token has expired", expired=True) from None
    except jwt.InvalidTokenError as exc:
        raise InvalidToken(f"Access token is not valid: {exc}") from None

    if claims.get("typ") != "access":
        raise InvalidToken("Wrong kind of token")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidToken("Token names no account")

    return subject
