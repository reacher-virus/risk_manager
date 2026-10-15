
"""
Request authentication + authorisation.

A request is authenticated by (in order): the HttpOnly session cookie, an
X-API-Key (machine clients), or, only when RISK_AUTH_REQUIRED=false and no
API keys exist, open dev mode.

Roles: viewer < analyst < admin.

Cookie sessions get CSRF protection on every state-changing method
(Origin check + signed double-submit token).

Role and account status are re-read from the database on every request,
so demotions and disablements apply at once.
"""

import hashlib
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import delete, func, select

from app.auth import netutil, tokens
from app.auth.models import AuthSession, RateEvent, User
from app.core import config as cfg
from app.core import db
from app.core.config import API_KEYS, RATE_LIMIT_PER_MIN


ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _rate_limit(identity: str) -> None:
    """Enforce a rolling 60-second API limit using shared database state."""
    if RATE_LIMIT_PER_MIN <= 0:
        return

    key = f"api:{identity}"
    now = db.utcnow()
    cutoff = now - timedelta(seconds=60)

    with db.session_scope() as s:
        # Serialize concurrent checks for the same identity on PostgreSQL.
        if s.bind.dialect.name == "postgresql":
            lock_id = int.from_bytes(
                hashlib.sha256(key.encode("utf-8")).digest()[:8],
                byteorder="big",
                signed=True,
            )
            s.execute(select(func.pg_advisory_xact_lock(lock_id)))

        count = s.execute(
            select(func.count())
            .select_from(RateEvent)
            .where(
                RateEvent.key == key,
                RateEvent.ts > cutoff,
            )
        ).scalar_one()

        if count >= RATE_LIMIT_PER_MIN:
            oldest = s.execute(
                select(func.min(RateEvent.ts)).where(
                    RateEvent.key == key,
                    RateEvent.ts > cutoff,
                )
            ).scalar_one()

            retry_after = 1
            if oldest is not None:
                retry_after = max(
                    1,
                    int(60 - (now - oldest).total_seconds()) + 1,
                )

            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        s.add(RateEvent(key=key, ts=now))


def reset_rate_limits() -> None:
    """Clear API rate-limit events; intended for test cleanup."""
    with db.session_scope() as s:
        s.execute(
            delete(RateEvent).where(RateEvent.key.like("api:%"))
        )


def _session_principal(request: Request, token: str) -> dict:
    claims = tokens.decode_access(token)

    with db.session_scope() as s:
        sess = s.get(AuthSession, claims["sid"])
        user = s.get(User, claims["sub"])
        now = db.utcnow()

        if (
            sess is None
            or user is None
            or sess.revoked_at is not None
            or sess.expires_at <= now
            or sess.user_id != user.id
            or user.status != "active"
            or user.token_version != claims.get("tv")
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session",
                headers={"WWW-Authenticate": "Cookie"},
            )

        who = {
            "actor": user.email,
            "role": user.role,
            "user_id": user.id,
            "session_id": sess.id,
            "via": "cookie",
            "is_admin_session": sess.is_admin,
        }

    # Only cookie-based sessions need CSRF protection.
    if request.method not in SAFE_METHODS:
        netutil.check_origin(request)

        if not tokens.csrf_ok(
            who["session_id"],
            request.headers.get("x-csrf-token"),
        ):
            raise HTTPException(
                status_code=403,
                detail="CSRF check failed",
            )

    return who


def principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict:
    cookie = request.cookies.get(tokens.cookie_names()["access"])

    if cookie:
        who = _session_principal(request, cookie)

    elif x_api_key is not None or (API_KEYS and not cfg.AUTH_REQUIRED):
        role = API_KEYS.get(x_api_key or "")

        if role is None:
            db.audit(
                "anonymous",
                "AUTH_FAILED",
                detail={"path": request.url.path},
            )
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid API key (send X-API-Key)",
            )

        who = {
            "actor": f"{role}-{x_api_key[:4]}",
            "role": role,
            "user_id": None,
            "session_id": None,
            "via": "apikey",
            "is_admin_session": False,
        }

    elif not cfg.AUTH_REQUIRED and not API_KEYS:
        who = {
            "actor": "dev",
            "role": "admin",
            "user_id": None,
            "session_id": None,
            "via": "dev",
            "is_admin_session": False,
        }

    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Cookie"},
        )

    if who["via"] == "apikey":
        identity = who["actor"]
    elif who["user_id"]:
        identity = f"user:{who['user_id']}"
    else:
        identity = (
            request.client.host
            if request.client
            else "local"
        )

    _rate_limit(identity)
    return who


def require_role(minimum: str):
    """Allow the specified role and higher-ranked roles."""
    if minimum not in ROLE_RANK:
        raise ValueError(f"Unknown role: {minimum}")

    def dep(p: dict = Depends(principal)) -> dict:
        if ROLE_RANK.get(p["role"], 0) < ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=403,
                detail=f"{minimum.capitalize()} role required",
            )
        return p

    return dep


require_analyst = require_role("analyst")
require_admin = require_role("admin")
