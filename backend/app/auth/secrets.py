"""
JWT / token secret management.

  * The secret comes from the environment (or a mounted file such as a Docker/K8s secret); it is never in the code.
  * Weak, short, placeholder or low-entropy secrets are REFUSED at startup, in every environment.
  * Production never auto-generates a secret. Development generates one into data/.jwt_secret (mode 0600).
  * Purpose-specific keys (JWT signing, OTP pepper, CSRF, webhook signing) are derived from the master secret with
    HKDF, so a leak of one use never exposes another and the raw env value is never used directly.
  * Rotation: set JWT_SECRET to the new value and JWT_SECRET_PREVIOUS to the old one. Tokens signed with the old key
    still verify (until they expire) but only the new key signs. Remove the old one after the longest token lifetime.
Generate a secret:   python -m app.auth.secrets
"""
import hashlib
import hmac
import logging
import math
import os
import secrets as pysecrets
from collections import Counter
from functools import lru_cache

from app.core import config as cfg

log = logging.getLogger("risk.auth")
MIN_LENGTH = 32
_PLACEHOLDERS = ("changeme", "change_me", "change-me", "password", "your-secret", "your_secret", "supersecret", "secretkey",
                 "secret_key", "jwt-secret", "jwtsecret", "example", "placeholder", "default", "replace", "insert", "todo")


class WeakSecretError(RuntimeError):
    pass


def _entropy_per_char(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def validate_secret(secret: str, name: str = "JWT_SECRET") -> str:
    if len(secret) < MIN_LENGTH:
        raise WeakSecretError(f"{name} must be at least {MIN_LENGTH} characters (got {len(secret)}). Generate one: python -m app.auth.secrets")
    low = secret.lower()
    if any(p in low for p in _PLACEHOLDERS):
        raise WeakSecretError(f"{name} looks like a placeholder/default value; use a randomly generated secret")
    if len(set(secret)) < 12 or _entropy_per_char(secret) < 3.0:
        raise WeakSecretError(f"{name} has too little randomness (repeated or patterned characters)")
    return secret


def _dev_secret_path():
    return cfg.DATA_DIR / ".jwt_secret"


def _read_master(name: str, env_value: str, file_value: str) -> str | None:
    if file_value:
        with open(file_value, encoding="utf-8") as f:
            return f.read().strip()
    return env_value.strip() or None


def _load_current() -> str:
    s = _read_master("JWT_SECRET", cfg.JWT_SECRET, cfg.JWT_SECRET_FILE)
    if s:
        return validate_secret(s)
    if cfg.IS_PROD:
        raise WeakSecretError("JWT_SECRET (or JWT_SECRET_FILE) must be set when APP_ENV=production. Generate one: python -m app.auth.secrets")
    path = _dev_secret_path()                                    # development only
    if path.exists():
        if path.stat().st_mode & 0o077:
            os.chmod(path, 0o600)
        return validate_secret(path.read_text().strip(), str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # created private from the first byte
    with os.fdopen(fd, "w") as f:
        f.write(pysecrets.token_urlsafe(48))
    log.warning("Generated a development JWT secret at %s. Set JWT_SECRET explicitly outside development.", path)
    return path.read_text().strip()


def hkdf(master: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-SHA256 (RFC 5869) with a fixed application salt."""
    prk = hmac.new(b"ai-risk-manager/v1", master, hashlib.sha256).digest()
    out, block = b"", b""
    for i in range(1, -(-length // 32) + 1):
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
    return out[:length]


@lru_cache(maxsize=1)
def _masters() -> tuple[bytes, bytes | None]:
    cur = _load_current().encode()
    prev_raw = cfg.JWT_SECRET_PREVIOUS.strip()
    prev = validate_secret(prev_raw, "JWT_SECRET_PREVIOUS").encode() if prev_raw else None
    return cur, prev


def reset_cache() -> None:
    _masters.cache_clear()


def subkey(purpose: str, previous: bool = False) -> bytes:
    cur, prev = _masters()
    master = prev if previous else cur
    if master is None:
        raise WeakSecretError("no previous secret configured")
    return hkdf(master, purpose.encode())


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def verification_keys() -> dict[str, bytes]:
    """kid -> JWT key, current first. Includes the previous key during a rotation window."""
    keys = {}
    cur = subkey("jwt")
    keys[key_id(cur)] = cur
    if _masters()[1] is not None:
        prev = subkey("jwt", previous=True)
        keys[key_id(prev)] = prev
    return keys


def mac(purpose: str, message: str) -> str:
    return hmac.new(subkey(purpose), message.encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":
    print(pysecrets.token_urlsafe(48))
