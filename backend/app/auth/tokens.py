"""Access JWTs, CSRF tokens and cookies."""
import hashlib
import secrets as pysecrets
import uuid
from datetime import timedelta

import jwt
from fastapi import HTTPException, Response

from app.auth import secrets as keys
from app.core import config as cfg
from app.core.db import utcnow

ALG = "HS256"                                  # pinned: the token header can never choose the algorithm
REQUIRED = ["exp", "iat", "nbf", "iss", "aud", "sub", "sid", "jti"]


def _unauthorized(msg: str = "Invalid or expired session") -> HTTPException:
    return HTTPException(401, msg, headers={"WWW-Authenticate": "Cookie"})


def issue_access(user_id: str, role: str, session_id: str, token_version: int, ttl_minutes: int) -> str:
    now = utcnow()
    key = keys.subkey("jwt")
    claims = {"iss": cfg.JWT_ISSUER, "aud": cfg.JWT_AUDIENCE, "sub": user_id, "sid": session_id, "tv": token_version, "role": role,
              "jti": uuid.uuid4().hex, "iat": now, "nbf": now, "exp": now + timedelta(minutes=ttl_minutes)}
    return jwt.encode(claims, key, algorithm=ALG, headers={"kid": keys.key_id(key)})


def decode_access(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALG:                                   # rejects alg=none and RS/HS confusion before any verification
            raise _unauthorized()
        key = keys.verification_keys().get(header.get("kid", ""))
        if key is None:
            raise _unauthorized()
        return jwt.decode(token, key, algorithms=[ALG], audience=cfg.JWT_AUDIENCE, issuer=cfg.JWT_ISSUER,
                          options={"require": REQUIRED}, leeway=5)
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise _unauthorized()


def new_refresh_token() -> tuple[str, str]:
    plain = pysecrets.token_urlsafe(48)                                 # 384 bits
    return plain, hashlib.sha256(plain.encode()).hexdigest()


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def csrf_for(session_id: str) -> str:
    return keys.mac("csrf", session_id)


def csrf_ok(session_id: str, presented: str | None) -> bool:
    import hmac
    return bool(presented) and hmac.compare_digest(csrf_for(session_id), presented)


def cookie_names() -> dict:
    p = "__Secure-" if cfg.COOKIE_SECURE else ""
    return {"access": p + "risk_access", "refresh": p + "risk_refresh", "csrf": p + "risk_csrf"}


def set_auth_cookies(resp: Response, access: str, refresh: str, session_id: str, access_ttl_s: int, refresh_ttl_s: int) -> None:
    n, common = cookie_names(), {"secure": cfg.COOKIE_SECURE, "domain": cfg.COOKIE_DOMAIN}
    resp.set_cookie(n["access"], access, max_age=access_ttl_s, path="/", httponly=True, samesite=cfg.COOKIE_SAMESITE, **common)
    resp.set_cookie(n["refresh"], refresh, max_age=refresh_ttl_s, path=cfg.COOKIE_REFRESH_PATH, httponly=True, samesite="strict", **common)
    # the CSRF token must be readable by the page's JavaScript so it can echo it in a header; it is useless without the HttpOnly cookies
    resp.set_cookie(n["csrf"], csrf_for(session_id), max_age=refresh_ttl_s, path="/", httponly=False, samesite=cfg.COOKIE_SAMESITE, **common)


def clear_auth_cookies(resp: Response) -> None:
    n, common = cookie_names(), {"secure": cfg.COOKIE_SECURE, "domain": cfg.COOKIE_DOMAIN}
    resp.delete_cookie(n["access"], path="/", httponly=True, samesite=cfg.COOKIE_SAMESITE, **common)
    resp.delete_cookie(n["refresh"], path=cfg.COOKIE_REFRESH_PATH, httponly=True, samesite="strict", **common)
    resp.delete_cookie(n["csrf"], path="/", samesite=cfg.COOKIE_SAMESITE, **common)
