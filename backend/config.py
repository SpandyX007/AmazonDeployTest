"""Every environment-driven knob, resolved once at import.

Reading settings here rather than at the call site means a misconfiguration
shows up at boot instead of on somebody's first login.
"""

from __future__ import annotations

import os
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


# --- sessions --------------------------------------------------------------

SESSION_COOKIE = os.getenv("SESSION_COOKIE_NAME", "sid")
SESSION_TTL_DAYS = _number("SESSION_TTL_DAYS", 30)
#: Renew a session's cookie once it is this far through its life, so an active
#: user is never logged out mid-thought while an idle one still expires.
SESSION_RENEW_AFTER = 0.5
#: How many browsers one account may stay signed in on; the oldest is dropped.
MAX_SESSIONS_PER_USER = _number("MAX_SESSIONS_PER_USER", 10)

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
