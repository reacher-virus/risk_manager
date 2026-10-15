"""Sign-up, two-step sign-in (+ dedicated admin sign-in), sessions, password reset. All state-changing public endpoints
check Origin, require a CAPTCHA where automation is the threat, and are rate limited per IP and per account."""
from contextlib import contextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.auth import captcha, netutil, ratelimit, service, tokens
from app.auth.models import AuthSession, RefreshToken, User
from app.auth.schemas import ChangePasswordIn, ForgotIn, LoginIn, ResendIn, ResetIn, SignupIn, VerifyIn
from app.core import config as cfg
from app.core import db
from app.core.security import principal

router = APIRouter(prefix="/auth", tags=["auth"])


@contextmanager
def auth_scope():
    """Like session_scope, but ALSO commits when an HTTPException is raised: failed-attempt counters, spent CAPTCHAs and
    consumed code attempts must persist even though the request is being rejected."""
    s = db.Session()
    try:
        yield s
        s.commit()
    except HTTPException:
        s.commit()
        raise
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def profile(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


def _pre(request: Request) -> str:
    netutil.check_origin(request)
    return netutil.client_ip(request)


@router.get("/captcha")
def get_captcha(request: Request):
    ip = netutil.client_ip(request)
    with auth_scope() as s:
        ratelimit.hit(s, f"captcha:ip:{ip}", cfg.RL_CAPTCHA_PER_IP)
        return captcha.create(s)


# ---------------------------------------------------------------- sign-up
@router.post("/signup", status_code=202)
def signup(body: SignupIn, request: Request, bg: BackgroundTasks):
    ip = _pre(request)
    with auth_scope() as s:
        if not captcha.verify(s, body.captcha_id, body.captcha_answer):
            raise HTTPException(400, "CAPTCHA incorrect or expired. Please try again.")
        return service.signup(s, bg, body.email, body.password, body.full_name, ip)


@router.post("/signup/verify")
def signup_verify(body: VerifyIn, request: Request):
    ip = _pre(request)
    with auth_scope() as s:
        user = service.signup_verify(s, body.challenge_id, body.code, ip)
        db.audit(user.email, "SIGNUP_VERIFIED", detail={"ip": ip}, session=s)
        return {"status": "verified", "message": "Email verified. You can now sign in."}


@router.post("/otp/resend", status_code=202)
def resend(body: ResendIn, request: Request, bg: BackgroundTasks):
    _pre(request)
    with auth_scope() as s:
        service.resend_challenge(s, body.challenge_id, bg)
    return {"message": "If the code is still valid, a new one has been sent."}


# ---------------------------------------------------------------- sign-in (user) and sign-in (admin): separate endpoints
def _login1(body: LoginIn, request: Request, bg: BackgroundTasks, admin: bool) -> dict:
    ip = _pre(request)
    with auth_scope() as s:
        ok = captcha.verify(s, body.captcha_id, body.captcha_answer)
        return service.login_step1(s, bg, body.email, body.password, ok, ip, admin)


def _login2(body: VerifyIn, request: Request, response: Response, admin: bool) -> dict:
    ip = _pre(request)
    with auth_scope() as s:
        user, access, refresh, a_ttl, r_ttl, sid = service.login_step2(s, body.challenge_id, body.code, ip, request.headers.get("user-agent", ""), admin)
        db.audit(user.email, "ADMIN_LOGIN" if admin else "LOGIN", detail={"ip": ip}, session=s)
        tokens.set_auth_cookies(response, access, refresh, sid, a_ttl, r_ttl)
        return {"user": profile(user), "admin_session": admin}


@router.post("/login")
def login(body: LoginIn, request: Request, bg: BackgroundTasks):
    return _login1(body, request, bg, admin=False)


@router.post("/login/verify")
def login_verify(body: VerifyIn, request: Request, response: Response):
    return _login2(body, request, response, admin=False)


@router.post("/admin/login")
def admin_login(body: LoginIn, request: Request, bg: BackgroundTasks):
    return _login1(body, request, bg, admin=True)


@router.post("/admin/login/verify")
def admin_login_verify(body: VerifyIn, request: Request, response: Response):
    return _login2(body, request, response, admin=True)


# ---------------------------------------------------------------- sessions
@router.get("/me")
def me(p: dict = Depends(principal)):
    if p["user_id"]:
        with db.session_scope() as s:
            u = s.get(User, p["user_id"])
            return {"authenticated": True, "via": "cookie", "admin_session": p["is_admin_session"], "user": profile(u)}
    return {"authenticated": True, "via": p["via"], "admin_session": False,
            "user": {"id": None, "email": p["actor"], "full_name": p["actor"], "role": p["role"], "created_at": None, "last_login_at": None}}


@router.post("/refresh")
def refresh(request: Request):
    ip = _pre(request)
    plain = request.cookies.get(tokens.cookie_names()["refresh"])
    try:
        if not plain:
            raise HTTPException(401, "Session expired")
        with auth_scope() as s:
            user, access, new_plain, a_ttl, r_ttl, sid = service.rotate_refresh(s, plain, request.headers.get("x-csrf-token"), ip, request.headers.get("user-agent", ""))
            resp = JSONResponse({"user": profile(user)})
            tokens.set_auth_cookies(resp, access, new_plain, sid, a_ttl, r_ttl)
            return resp
    except HTTPException as e:
        if e.status_code == 401:                                        # dead session: also drop the browser's cookies
            resp = JSONResponse({"detail": e.detail}, status_code=401)
            tokens.clear_auth_cookies(resp)
            return resp
        raise


@router.post("/logout")
def logout(request: Request):
    ip = _pre(request)
    n = tokens.cookie_names()
    with auth_scope() as s:
        sid = None
        if (access := request.cookies.get(n["access"])):
            try:
                sid = tokens.decode_access(access)["sid"]
            except HTTPException:
                pass
        if sid is None and (refresh_c := request.cookies.get(n["refresh"])):
            rt = s.get(RefreshToken, tokens.hash_token(refresh_c))
            sid = rt.session_id if rt else None
        if sid:
            sess = s.get(AuthSession, sid)
            if sess:
                service.revoke_session(s, sid)
                u = s.get(User, sess.user_id)
                db.audit(u.email if u else "unknown", "LOGOUT", detail={"ip": ip}, session=s)
    resp = JSONResponse({"ok": True})
    tokens.clear_auth_cookies(resp)
    return resp


@router.post("/logout-all")
def logout_all(p: dict = Depends(principal)):
    if not p["user_id"]:
        raise HTTPException(400, "Only signed-in users have sessions")
    with auth_scope() as s:
        u = s.get(User, p["user_id"])
        u.token_version += 1
        service.revoke_all_sessions(s, u.id)
    db.audit(p["actor"], "LOGOUT_ALL")
    resp = JSONResponse({"ok": True})
    tokens.clear_auth_cookies(resp)
    return resp


# ---------------------------------------------------------------- password reset / change
@router.post("/password/forgot", status_code=202)
def forgot(body: ForgotIn, request: Request, bg: BackgroundTasks):
    ip = _pre(request)
    with auth_scope() as s:
        ok = captcha.verify(s, body.captcha_id, body.captcha_answer)
        return service.forgot_password(s, bg, body.email, ok, ip)


@router.post("/password/reset")
def reset(body: ResetIn, request: Request, bg: BackgroundTasks):
    ip = _pre(request)
    with auth_scope() as s:
        service.reset_password(s, bg, body.token, body.new_password, ip)
    return {"message": "Password updated. Please sign in again."}


@router.post("/password/change")
def change(body: ChangePasswordIn, bg: BackgroundTasks, p: dict = Depends(principal)):
    if not p["user_id"]:
        raise HTTPException(400, "Only signed-in users have a password")
    with auth_scope() as s:
        service.change_password(s, bg, s.get(User, p["user_id"]), body.current_password, body.new_password)
    resp = JSONResponse({"message": "Password changed. Please sign in again."})
    tokens.clear_auth_cookies(resp)
    return resp
