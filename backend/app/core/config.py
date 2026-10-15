"""Central configuration. Everything is overridable via environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("RISK_DATA_DIR", BASE_DIR / "data"))
RAW_PATH = DATA_DIR / "raw" / "transactions_synthetic.csv"
PROCESSED_PATH = DATA_DIR / "processed" / "features.csv"
MODEL_DIR = DATA_DIR / "models"
for _p in (RAW_PATH.parent, PROCESSED_PATH.parent, MODEL_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# SQLite by default; set DATABASE_URL=postgresql+psycopg2://user:pw@host/db for PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/risk.db")

# Chargebacks/returns/fraud confirmations arrive late in the real world. History features
# only see an outcome this many days after the transaction happened (leakage prevention).
LABEL_DELAY_DAYS = float(os.getenv("RISK_LABEL_DELAY_DAYS", "14"))

# Default business costs (INR); overridable at runtime from the dashboard.
COST_FP = float(os.getenv("RISK_COST_FP", "150"))
COST_FN = float(os.getenv("RISK_COST_FN", "2500"))


def _parse_keys(raw: str) -> dict:
    """API_KEYS="abc123:admin,def456:analyst" -> {"abc123": "admin", ...}. Empty = auth disabled (dev mode)."""
    out = {}
    for part in filter(None, (p.strip() for p in raw.split(","))):
        key, _, role = part.partition(":")
        out[key] = role or "analyst"
    return out


API_KEYS = _parse_keys(os.getenv("API_KEYS", ""))
RATE_LIMIT_PER_MIN = int(os.getenv("RISK_RATE_LIMIT_PER_MIN", "240"))

# Rows in the first WARMUP_DAYS have no history/labels yet; excluded from training and evaluation.
WARMUP_DAYS = float(os.getenv("RISK_WARMUP_DAYS", "14"))


# =====================================================================================
# Authentication & security. Read these as `cfg.NAME` (not `from ... import NAME`) so they can be overridden in tests.
# =====================================================================================
def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


APP_ENV = os.getenv("APP_ENV", "development").lower()           # "production" turns on strict startup checks
IS_PROD = APP_ENV == "production"
AUTH_REQUIRED = _bool("RISK_AUTH_REQUIRED", True)                # False = open dev mode (tests / quick local poking only)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")   # used to BUILD reset links (never the Host header)
CORS_ORIGINS = _list("CORS_ORIGINS", FRONTEND_URL)               # explicit origins only: cookies + "*" is forbidden

# ---- transport ----
FORCE_HTTPS = _bool("FORCE_HTTPS", IS_PROD)                      # redirect http->https and send HSTS
COOKIE_SECURE = _bool("COOKIE_SECURE", IS_PROD)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()    # lax | strict (refresh cookie is always strict)
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
TRUSTED_PROXY_COUNT = _int("TRUSTED_PROXY_COUNT", 0)             # >0 only behind your own reverse proxy (reads X-Forwarded-*)

# ---- secrets (see app/auth/secrets.py) ----
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_SECRET_FILE = os.getenv("JWT_SECRET_FILE", "")               # e.g. a Docker/K8s secret mount
JWT_SECRET_PREVIOUS = os.getenv("JWT_SECRET_PREVIOUS", "")       # accepted for VERIFYING only, during rotation
JWT_ISSUER, JWT_AUDIENCE = "ai-risk-manager", "ai-risk-manager-web"

# ---- sessions ----
ACCESS_TTL_MIN = _int("ACCESS_TTL_MIN", 15)
REFRESH_TTL_HOURS = _int("REFRESH_TTL_HOURS", 24 * 7)
SESSION_MAX_DAYS = _int("SESSION_MAX_DAYS", 14)                  # absolute lifetime, however often it is refreshed
ADMIN_ACCESS_TTL_MIN = _int("ADMIN_ACCESS_TTL_MIN", 10)
ADMIN_REFRESH_TTL_HOURS = _int("ADMIN_REFRESH_TTL_HOURS", 2)
ADMIN_SESSION_MAX_HOURS = _int("ADMIN_SESSION_MAX_HOURS", 8)
ADMIN_ALLOWED_IPS = _list("ADMIN_ALLOWED_IPS")                   # optional CIDRs, e.g. "203.0.113.0/24,10.0.0.5"

# ---- multi-step auth ----
OTP_TTL_MIN = _int("OTP_TTL_MIN", 10)
OTP_MAX_ATTEMPTS = _int("OTP_MAX_ATTEMPTS", 5)
OTP_RESEND_COOLDOWN_S = _int("OTP_RESEND_COOLDOWN_S", 60)
CAPTCHA_TTL_S = _int("CAPTCHA_TTL_S", 300)
RESET_TOKEN_TTL_MIN = _int("RESET_TOKEN_TTL_MIN", 30)

# ---- email ----
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_SSL = _bool("SMTP_SSL", False)                              # True = implicit TLS (port 465); False = STARTTLS
MAIL_FROM = os.getenv("MAIL_FROM", "Risk Manager <no-reply@localhost>")
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
AUTH_CHECK_MX = _bool("AUTH_CHECK_MX", IS_PROD)                  # reject domains that cannot receive mail (needs DNS)
ALLOWED_EMAIL_DOMAINS = [d.lower() for d in _list("ALLOWED_EMAIL_DOMAINS")]   # optional allowlist, e.g. your company

# ---- rate limits: (max events, window seconds). Stored in the DB so they survive restarts and work across workers ----
RL_LOGIN_FAIL_PER_ACCOUNT = (5, 15 * 60)       # failed password attempts per email, then locked out for the window
RL_LOGIN_PER_IP = (30, 15 * 60)
RL_SIGNUP_PER_IP = (8, 60 * 60)
RL_SIGNUP_PER_EMAIL = (3, 60 * 60)
RL_FORGOT_PER_IP = (8, 60 * 60)
RL_FORGOT_PER_EMAIL = (3, 60 * 60)
RL_VERIFY_PER_IP = (30, 15 * 60)
RL_CAPTCHA_PER_IP = (60, 15 * 60)

# ---- bootstrap & outbound ----
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")                       # optional: create the first admin at startup
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
WEBHOOK_ALLOWED_PORTS = [int(p) for p in _list("WEBHOOK_ALLOWED_PORTS", "443,8443")]
WEBHOOK_ALLOWED_HOSTS = [h.lower() for h in _list("WEBHOOK_ALLOWED_HOSTS")]   # optional hostname-suffix allowlist
COOKIE_REFRESH_PATH = os.getenv("COOKIE_REFRESH_PATH", "/auth")   # behind a proxy that mounts the API at /api use /api/auth
ALLOWED_HOSTS = _list("ALLOWED_HOSTS")     # Host-header allowlist (production: your domain). Empty = not enforced.
