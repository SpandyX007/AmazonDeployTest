"""Every environment-driven knob, resolved once at import.

Reading settings here rather than at the call site means a misconfiguration
shows up at boot instead of on somebody's first login.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import quote_plus

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


def _decimal(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


def _csv(name: str, default: str = "") -> frozenset[str]:
    raw = os.getenv(name)
    value = default if raw is None else raw
    return frozenset(item.strip() for item in value.split(",") if item.strip())


# --- storage: AWS RDS PostgreSQL --------------------------------------------
#
# One engine everywhere. Dev and prod both talk to Postgres, so the schema that
# boots on a laptop is the schema that boots on the box — there is no SQLite
# fallback to paper over a dialect difference until it is too late to notice.
#
# Either hand over a full DATABASE_URL, or the parts and the URL is assembled
# here. The part names match the RDS PoC's .env so the same values carry over.

DB_HOST = os.getenv("DB_HOST", "").strip()
DB_PORT = _number("DB_PORT", 5432)
#: A fresh RDS instance ships with only the default `postgres` database;
#: `backend.db.init_db` creates this one on first boot if it is missing.
DB_NAME = os.getenv("DB_NAME", "").strip() or "nexus"
DB_USER = os.getenv("DB_USER", "").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def _database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    if not (DB_HOST and DB_USER):
        raise RuntimeError(
            "No database configured: set DB_HOST, DB_USER and DB_PASSWORD "
            "(or a full DATABASE_URL) in backend/.env — see backend/.env.example."
        )
    # quote_plus: a password containing '@' or '/' must not be read as URL syntax.
    return (
        f"postgresql+psycopg://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


DATABASE_URL = _database_url()

#: RDS enforces TLS (`rds.force_ssl`). `verify-full` goes further and checks
#: the server's certificate against Amazon's CA bundle, so a hijacked DNS name
#: cannot point us at a look-alike host. The bundle is public — it ships in the
#: repo and the image. Set DB_SSLMODE=disable only for a Postgres on localhost.
DB_SSL_ROOT_CERT = Path(os.getenv("DB_SSL_ROOT_CERT", "").strip() or "global-bundle.pem")
if not DB_SSL_ROOT_CERT.is_absolute():
    DB_SSL_ROOT_CERT = BACKEND_DIR / DB_SSL_ROOT_CERT
DB_SSLMODE = os.getenv("DB_SSLMODE", "").strip().lower() or (
    "verify-full" if DB_SSL_ROOT_CERT.is_file() else "require"
)

#: Handed to psycopg as libpq parameters. `connect_timeout` keeps a wrong
#: security group from hanging the boot: it fails in seconds, with a message.
DB_CONNECT_ARGS: dict[str, object] = {
    "sslmode": DB_SSLMODE,
    "connect_timeout": _number("DB_CONNECT_TIMEOUT", 10),
}
if DB_SSLMODE in {"verify-ca", "verify-full"}:
    if not DB_SSL_ROOT_CERT.is_file():
        raise RuntimeError(
            f"DB_SSLMODE={DB_SSLMODE} needs the RDS CA bundle, but {DB_SSL_ROOT_CERT} is "
            "missing. Download https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem "
            "into backend/, or point DB_SSL_ROOT_CERT at it."
        )
    DB_CONNECT_ARGS["sslrootcert"] = str(DB_SSL_ROOT_CERT)

#: Connections held open per process, and how many more may be opened under
#: load before callers queue. Every worker and every instance draws on the
#: same RDS connection cap (roughly a hundred on a micro instance), so keep
#: the product of those numbers small.
DB_POOL_SIZE = _number("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW = _number("DB_MAX_OVERFLOW", 10)


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
#: Hard cap on one reply. This is what bounds the overdraw: a turn's cost is
#: unknown until it ends, so a balance of 1 credit can still run one full
#: reply — but never more than this many tokens of one.
MAX_COMPLETION_TOKENS = _number("MAX_COMPLETION_TOKENS", 2048)


# --- credits & pricing -----------------------------------------------------
#
# Usage is metered in *credits*, not vendor tokens. One credit is one token on
# a free-tier model; premium models charge a multiple of that per token. Keeping
# the unit ours means three vendors with three tokenizers still draw down one
# balance, and a price change is a config edit rather than a migration.

#: Every new account starts with this many credits, for free.
FREE_SIGNUP_CREDITS = _number("FREE_SIGNUP_CREDITS", 20_000)

#: The one pack on sale: pay PAID_PACK_PRICE_INR, receive PAID_PACK_CREDITS
#: and premium access. There is no gateway — the user pays a UPI QR and
#: submits the transaction reference, which the owner approves by hand.
PAID_PACK_PRICE_INR = _number("PAID_PACK_PRICE_INR", 10)
PAID_PACK_CREDITS = _number("PAID_PACK_CREDITS", 200_000)

#: Credits charged per token. Premium models cost this multiple of free ones.
FREE_CREDITS_PER_TOKEN = _decimal("FREE_CREDITS_PER_TOKEN", 1.0)
PREMIUM_CREDITS_PER_TOKEN = _decimal("PREMIUM_CREDITS_PER_TOKEN", 5.0)

#: Which models are premium. A model is premium when its catalog `speed` is in
#: PREMIUM_SPEEDS (this is what sorts Ollama's discovered models by size), or
#: it is listed in PREMIUM_MODELS. FREE_MODELS overrides in the other direction.
#: Entries are model ids, optionally qualified as `provider:model`.
PREMIUM_SPEEDS = _csv("PREMIUM_SPEEDS", "Balanced,Deep")
PREMIUM_MODELS = _csv("PREMIUM_MODELS")
FREE_MODELS = _csv("FREE_MODELS")


# --- UPI (manual payments) -------------------------------------------------

#: The VPA the QR code points at, e.g. yourname@okaxis. Leave blank to hide
#: the pay flow entirely — models stay locked but nobody is told to pay.
UPI_ID = os.getenv("UPI_ID", "").strip()
UPI_PAYEE_NAME = os.getenv("UPI_PAYEE_NAME", "").strip()
#: Optional: a PNG/JPG/SVG of your own QR (e.g. the one your bank app gives
#: you) to serve instead of one generated from UPI_ID.
UPI_QR_IMAGE = os.getenv("UPI_QR_IMAGE", "").strip()
