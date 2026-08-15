"""Every environment-driven knob, resolved once at import.

Reading settings here rather than at the call site means a misconfiguration
shows up at boot instead of on somebody's first login.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

# Same file the provider registry reads; loading it twice is harmless.
load_dotenv(BACKEND_DIR / ".env")


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


# --- storage ---------------------------------------------------------------

#: SQLite by default so the app boots with zero setup. Point this at
#: postgresql+psycopg://user:pass@host/db in production — nothing else changes.
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"


# --- JWT ------------------------------------------------------------------

#: Signing key for access tokens. There is deliberately no default: a shipped
#: fallback secret is a shipped forgery key, since anyone holding it can mint a
#: token for any account. In dev we generate an ephemeral one instead, which
#: costs nothing but a re-login after each restart.
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_SECRET_IS_EPHEMERAL = not JWT_SECRET
if JWT_SECRET_IS_EPHEMERAL:
    JWT_SECRET = secrets.token_urlsafe(48)

#: HMAC, not RSA: one service both signs and verifies, so there is no second
#: party who needs a public key. Swap to RS256 the day something else must
#: verify these tokens without being able to issue them.
JWT_ALGORITHM = "HS256"
#: Stamped as `iss` and checked on the way back in, so a token minted by some
#: other service that happens to share a secret is still rejected.
JWT_ISSUER = os.getenv("JWT_ISSUER", "nexus")

#: Short by design. An access token cannot be revoked before it expires, so its
#: lifetime *is* the window a stolen one stays useful — keep it in minutes.
ACCESS_TOKEN_TTL_MINUTES = _number("ACCESS_TOKEN_TTL_MINUTES", 15)
#: The refresh token carries the long-lived half of the session and is revocable,
#: because unlike the access token it is checked against a database row.
REFRESH_TOKEN_TTL_DAYS = _number("REFRESH_TOKEN_TTL_DAYS", 30)
#: How many browsers one account may stay signed in on; the oldest is dropped.
MAX_SESSIONS_PER_USER = _number("MAX_SESSIONS_PER_USER", 10)
#: Two tabs can hit /refresh with the same token in the same instant. Inside
#: this window that reads as a race and is forgiven; outside it, the same token
#: turning up twice means it leaked, and the whole session chain is burned.
REFRESH_REUSE_GRACE_SECONDS = _number("REFRESH_REUSE_GRACE_SECONDS", 10)


# --- refresh cookie --------------------------------------------------------

REFRESH_COOKIE = os.getenv("REFRESH_COOKIE_NAME", "rt")
#: Scoped to the auth routes, so the refresh token is simply not attached to
#: the hundreds of ordinary API calls that have no business seeing it.
REFRESH_COOKIE_PATH = "/api/auth"

#: Must be on behind HTTPS. Off by default so http://localhost works in dev.
COOKIE_SECURE = _flag("COOKIE_SECURE", False)
#: "lax" keeps the cookie off cross-site POSTs, which is most of our CSRF story.
#: A frontend on a different site than the API needs "none" plus COOKIE_SECURE.
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()


# --- login throttle --------------------------------------------------------

LOGIN_MAX_ATTEMPTS = _number("LOGIN_MAX_ATTEMPTS", 8)
#: Far looser than the per-email limit on purpose: a whole office behind one
#: NAT address shares an IP, so a tight limit here would let one attacker lock
#: out every colleague. It exists to slow spraying across many accounts.
LOGIN_MAX_ATTEMPTS_PER_IP = _number("LOGIN_MAX_ATTEMPTS_PER_IP", LOGIN_MAX_ATTEMPTS * 5)
LOGIN_LOCKOUT_SECONDS = _number("LOGIN_LOCKOUT_SECONDS", 900)


# --- chat memory -----------------------------------------------------------

#: How many stored messages of a thread get replayed to the model. Older turns
#: stay in the database and on screen — they just stop being sent upstream, so
#: a long thread cannot grow past the model's context window.
MEMORY_WINDOW_MESSAGES = _number("MEMORY_WINDOW_MESSAGES", 40)
#: Prepended to every thread that has no system prompt of its own.
DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT", "").strip()
