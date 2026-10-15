"""Admin-only: user management and the alert webhook. Admin accounts themselves are managed from the server console
(python -m app.auth.create_admin), never through the API, so a hijacked admin session cannot mint more admins."""
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.routes_auth import auth_scope, profile
from app.auth import service
from app.auth.models import User
from app.core import db, ssrf
from app.core import webhook as webhook_mod
from app.core.security import require_admin
from app.auth import secrets as keys

router = APIRouter(prefix="/admin", tags=["admin"])


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Optional[Literal["viewer", "analyst"]] = None          # "admin" is deliberately not assignable here
    status: Optional[Literal["active", "disabled"]] = None


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: Optional[str] = Field(default=None, max_length=2048)


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"      # user input is data, never a pattern


@router.get("/users")
def list_users(q: str = Query("", max_length=100), role: Optional[Literal["viewer", "analyst", "admin"]] = None,
               status: Optional[Literal["active", "disabled"]] = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
               p: dict = Depends(require_admin)):
    stmt = select(User)
    if q:
        stmt = stmt.where(User.email.ilike(_like(q.lower()), escape="\\") | User.full_name.ilike(_like(q), escape="\\"))
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    with db.session_scope() as s:
        total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = s.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)).scalars().all()
        return {"total": total, "items": [{**profile(u), "status": u.status, "email_verified": u.email_verified} for u in rows]}


def _target(s, user_id: str, actor: dict) -> User:
    u = s.get(User, user_id) if re.fullmatch(r"[0-9a-f]{32}", user_id) else None
    if u is None:
        raise HTTPException(404, "User not found")
    if u.role == "admin":
        raise HTTPException(403, "Admin accounts are managed from the server console")
    if u.id == actor.get("user_id"):
        raise HTTPException(403, "You cannot change your own account here")
    return u


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserPatch, p: dict = Depends(require_admin)):
    if body.role is None and body.status is None:
        raise HTTPException(422, "Nothing to change")
    with auth_scope() as s:
        u = _target(s, user_id, p)
        if body.role:
            u.role = body.role
        if body.status:
            u.status = body.status
            if body.status == "disabled":
                u.token_version += 1
                service.revoke_all_sessions(s, u.id)
        db.audit(p["actor"], "USER_UPDATED", detail={"user": u.email, "role": body.role, "status": body.status}, session=s)
        return {**profile(u), "status": u.status}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: str, p: dict = Depends(require_admin)):
    with auth_scope() as s:
        u = _target(s, user_id, p)
        u.token_version += 1
        service.revoke_all_sessions(s, u.id)
        db.audit(p["actor"], "USER_SESSIONS_REVOKED", detail={"user": u.email}, session=s)
    return {"ok": True}


# ---------------------------------------------------------------- webhook (outbound => SSRF-guarded)
@router.get("/webhook")
def get_webhook(p: dict = Depends(require_admin)):
    return {"url": db.get_setting("webhook_url")}


@router.put("/webhook")
def set_webhook(body: WebhookIn, p: dict = Depends(require_admin)):
    if body.url:
        try:
            ssrf.validate_public_url(body.url)
        except ssrf.UnsafeURL as e:
            raise HTTPException(422, f"Webhook URL rejected: {e}")
        db.set_setting("webhook_url", body.url)
    else:
        with db.session_scope() as s:
            row = s.get(db.Setting, "webhook_url")
            if row:
                s.delete(row)
    db.audit(p["actor"], "WEBHOOK_CONFIG", detail={"set": bool(body.url)})
    return {"url": body.url or None}


@router.post("/webhook/test")
def test_webhook(p: dict = Depends(require_admin)):
    url = db.get_setting("webhook_url")
    if not url:
        raise HTTPException(422, "No webhook configured")
    try:
        status = ssrf.post_json(url, {"event": "test", "message": "Risk Manager webhook test"}, keys.subkey("webhook"))
    except ssrf.UnsafeURL as e:
        raise HTTPException(422, f"Webhook URL rejected: {e}")
    except Exception as e:
        raise HTTPException(502, f"Delivery failed ({type(e).__name__})")
    return {"delivered": 200 <= status < 300, "status": status}
