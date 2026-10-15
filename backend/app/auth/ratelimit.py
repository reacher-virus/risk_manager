"""DB-backed sliding-window rate limiting for authentication. Survives restarts and works across worker processes.
Keys look like "login-fail:acct:<email>" or "login:ip:<ip>"; unknown accounts are counted exactly like real ones."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.auth.models import RateEvent
from app.core.db import utcnow


def _count_and_oldest(session, key: str, window: int):
    since = utcnow() - timedelta(seconds=window)
    return session.execute(select(func.count(RateEvent.id), func.min(RateEvent.ts)).where(RateEvent.key == key, RateEvent.ts > since)).one()


def _too_many(oldest, window: int) -> HTTPException:
    retry = max(1, int(window - (utcnow() - oldest).total_seconds())) if oldest else window
    return HTTPException(429, "Too many attempts. Please wait and try again.", headers={"Retry-After": str(retry)})


def check(session, key: str, limit: tuple[int, int]) -> None:
    """Raise 429 if the key is already at its limit (does not record)."""
    n, oldest = _count_and_oldest(session, key, limit[1])
    if n >= limit[0]:
        raise _too_many(oldest, limit[1])


def record(session, key: str) -> None:
    session.add(RateEvent(key=key))
    session.flush()


def hit(session, key: str, limit: tuple[int, int]) -> None:
    """Check, then record. The standard path for per-IP and per-email caps."""
    check(session, key, limit)
    record(session, key)


def clear(session, key: str) -> None:
    session.execute(delete(RateEvent).where(RateEvent.key == key))


def purge(session, older_than_seconds: int = 24 * 3600) -> None:
    session.execute(delete(RateEvent).where(RateEvent.ts < utcnow() - timedelta(seconds=older_than_seconds)))
