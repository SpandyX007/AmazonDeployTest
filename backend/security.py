"""Password hashing, session tokens, and a small brute-force brake.

Nothing here touches the database or FastAPI — it is pure crypto plumbing, so
it can be reasoned about (and tested) on its own.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from functools import lru_cache
from typing import Mapping

import bcrypt

from backend.config import LOGIN_LOCKOUT_SECONDS


# --- passwords -------------------------------------------------------------


def _prepare(password: str) -> bytes:
    """Fold a password into a fixed-width digest before bcrypt sees it.

    bcrypt silently ignores everything past 72 bytes, so without this a long
    passphrase would quietly lose its tail. SHA-256 + base64 lands at 44 bytes
    whatever the input, keeping the full entropy of what the user typed.
    """
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode())
    except ValueError:
        # A malformed hash in the row — treat as "does not match", never crash
        # the login route.
        return False


@lru_cache(maxsize=1)
def _decoy_hash() -> bytes:
    return bcrypt.hashpw(_prepare("decoy"), bcrypt.gensalt())


def burn_password_time() -> None:
    """Spend one bcrypt verification against a throwaway hash.

    Called when the email is unknown, so "no such account" takes the same time
    as "wrong password" and the response cannot be used to enumerate users.
    """
    bcrypt.checkpw(_prepare("decoy"), _decoy_hash())


# --- session tokens --------------------------------------------------------


def new_session_token() -> str:
    """256 bits of URL-safe randomness. This value only ever exists in the
    cookie and in transit — the database stores its hash."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # A session token is already high-entropy random, so a fast hash is right
    # here: there is no dictionary to attack, and lookups happen per request.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- login throttle --------------------------------------------------------


class LoginThrottle:
    """In-process counter of recent failed logins.

    Each caller decides what to count and how tightly: the login route keys on
    both the email and the client IP, with a much looser limit on the IP so a
    shared office address cannot be used to lock everyone out.

    Deliberately modest: it blunts password spraying against a single box. It
    resets on restart and is per-worker, so a multi-process or multi-instance
    deployment wants Redis or a WAF rule instead of this.
    """

    def __init__(self, window_seconds: int, cap: int = 500) -> None:
        self._window = window_seconds
        self._cap = cap
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        return [t for t in self._hits.get(key, []) if now - t < self._window]

    def retry_after(self, checks: Mapping[str, int]) -> int:
        """Seconds the caller must wait, or 0 if they may try now.

        `checks` maps each key to the number of failures it tolerates.
        """
        now = time.monotonic()
        waits = []
        with self._lock:
            for key, limit in checks.items():
                hits = self._recent(key, now)
                if len(hits) >= limit:
                    # Once the limit-th most recent failure ages out of the
                    # window, the count drops back under the limit.
                    waits.append(int(self._window - (now - hits[-limit])) + 1)
        return max([w for w in waits if w > 0], default=0)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._hits[key] = [*self._recent(key, now), now][-self._cap :]

    def clear(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._hits.pop(key, None)


login_throttle = LoginThrottle(LOGIN_LOCKOUT_SECONDS)
