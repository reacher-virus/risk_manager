"""Password hashing (Argon2id) and policy."""
import os
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core import config as cfg

_fast = os.getenv("RISK_ARGON2_FAST") == "1" and not cfg.IS_PROD       # tests only; ignored in production
_ph = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1) if _fast else PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy: str | None = None

COMMON = {
    "password", "password1", "password123", "123456789012", "qwertyuiopas", "qwerty123456", "iloveyou1234", "admin1234567",
    "welcome12345", "letmein12345", "changeme1234", "abc123456789", "monkey123456", "dragon123456", "football1234",
    "baseball1234", "sunshine1234", "princess1234", "trustno1trustno1", "passw0rd1234", "p@ssw0rd1234", "1q2w3e4r5t6y",
    "riskmanager", "riskmanager1", "frauddetect", "administrator", "administrator1",
}
_SEQ = "abcdefghijklmnopqrstuvwxyz0123456789qwertyuiopasdfghjklzxcvbnm"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-effort check: an unknown account still burns one full Argon2 verification (no timing oracle)."""
    global _dummy
    if stored_hash is None:
        _dummy = _dummy or _ph.hash("timing-equaliser-not-a-real-password")
        try:
            _ph.verify(_dummy, password)
        except (VerificationError, InvalidHashError):
            pass
        return False
    try:
        return _ph.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _ph.check_needs_rehash(stored_hash)


def validate_password(password: str, email: str = "", name: str = "") -> list[str]:
    """Return a list of problems (empty = acceptable)."""
    problems = []
    if len(password) < 12:
        problems.append("must be at least 12 characters")
    if len(password) > 128:
        problems.append("must be at most 128 characters")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3 and len(password) < 20:
        problems.append("must mix at least 3 of: lowercase, uppercase, digits, symbols (or be 20+ characters)")
    core = re.sub(r"[\d\W_]+$", "", password.lower())
    if password.lower() in COMMON or core in COMMON or any(c in password.lower() for c in ("password", "qwerty", "letmein")):
        problems.append("is too common")
    low = password.lower()
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in low:
        problems.append("must not contain your email name")
    if any(len(tok) >= 4 and tok in low for tok in re.split(r"\W+", name.lower())):
        problems.append("must not contain your name")
    if re.search(r"(.)\1{3,}", password):
        problems.append("must not repeat a character 4+ times in a row")
    if any(_SEQ[i:i + 5] in low or _SEQ[i:i + 5][::-1] in low for i in range(len(_SEQ) - 4)):
        problems.append("must not contain keyboard or alphabet sequences like 12345 or abcde")
    return problems
