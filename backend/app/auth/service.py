"""Authentication business logic. Every function takes an open DB session; routes own the transaction.

Design rules enforced here
  * Generic errors: login / sign-up / reset never reveal whether an email is registered.
  * Equal effort: unknown accounts still pay for a full Argon2 verification.
  * One-time codes are HMAC'd, attempt-limited atomically, single-use and short-lived.
  * Refresh tokens rotate; presenting a spent one burns the whole session (theft detection).
  * Unverified sign-ups are not users: their data waits on the challenge until the emailed code proves the mailbox.
"""
import hashlib
import hmac
import json
import secrets as pysecrets
import unicodedata
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from app.auth import identity, mailer, passwords, ratelimit, tokens
from app.auth import secrets as keys
from app.auth.models import AuthSession, MfaChallenge, PasswordResetToken, RefreshToken, User, new_id
from app.core import config as cfg
from app.core import db
from app.core.db import utcnow

GENERIC_LOGIN = "Invalid email, password or CAPTCHA."
GENERIC_CODE = "Invalid or expired code."
GENERIC_RESET = "Invalid or expired reset link."
SIGNUP_MESSAGE = "If the details are valid, we have emailed a 6-digit verification code."
RESET_MESSAGE = "If an account exists for that email, a password reset link has been sent."


def fail(status: int, detail: str) -> HTTPException:
    return HTTPException(status, detail)


def light_email(raw: str) -> str:
    """For lookups only (login/forgot): canonicalise without the strict signup checks (no DNS, no disposable list)."""
    raw = unicodedata.normalize("NFKC", raw or "").strip().lower()
    if not raw or len(raw) > 254 or any(ord(c) < 32 for c in raw):
        return ""
    return raw


# ------------------------------------------------------------------ one-time codes
def _code_hash(challenge_id: str, code: str) -> str:
    return keys.mac("otp", f"{challenge_id}:{code}")


def _new_code() -> str:
    return f"{pysecrets.randbelow(10 ** 6):06d}"


def issue_challenge(session, user_id: str | None, purpose: str, ip: str, payload: dict | None = None, decoy: bool = False) -> tuple[MfaChallenge, str]:
    if user_id:                                                           # a new code supersedes older unused ones
        session.execute(update(MfaChallenge).where(MfaChallenge.user_id == user_id, MfaChallenge.purpose == purpose,
                                                   MfaChallenge.used_at.is_(None)).values(used_at=utcnow()))
    cid = new_id()
    code = _new_code()
    ch = MfaChallenge(id=cid, user_id=user_id, purpose=purpose, ip=ip,
                      code_hash=_code_hash(cid, pysecrets.token_hex(8) if decoy else code),   # decoy: nothing can ever match
                      expires_at=utcnow() + timedelta(minutes=cfg.OTP_TTL_MIN), payload=json.dumps(payload) if payload else None)
    session.add(ch)
    session.flush()
    return ch, code


def check_challenge(session, challenge_id: str, code: str, purpose: str) -> MfaChallenge | None:
    """Return the challenge if the code is right; otherwise None. Attempts are counted atomically in the database."""
    ch = session.execute(select(MfaChallenge).where(MfaChallenge.id == challenge_id, MfaChallenge.purpose == purpose)).scalar_one_or_none()
    if ch is None:
        return None
    counted = session.execute(update(MfaChallenge).where(
        MfaChallenge.id == challenge_id, MfaChallenge.used_at.is_(None), MfaChallenge.expires_at > utcnow(),
        MfaChallenge.attempts < cfg.OTP_MAX_ATTEMPTS).values(attempts=MfaChallenge.attempts + 1)).rowcount
    if counted != 1:
        return None                                                       # expired, spent, or out of attempts
    if not hmac.compare_digest(ch.code_hash, _code_hash(challenge_id, code)):
        return None
    spent = session.execute(update(MfaChallenge).where(MfaChallenge.id == challenge_id, MfaChallenge.used_at.is_(None))
                            .values(used_at=utcnow())).rowcount
    return ch if spent == 1 else None


def resend_challenge(session, challenge_id: str, bg) -> None:
    """New code for the same challenge (cooldown + hourly cap). Silent for unknown/decoy ids so nothing leaks."""
    ratelimit.hit(session, f"otp-resend:{challenge_id}", (1, cfg.OTP_RESEND_COOLDOWN_S))
    ratelimit.hit(session, f"otp-resend-total:{challenge_id}", (5, 3600))
    ch = session.execute(select(MfaChallenge).where(MfaChallenge.id == challenge_id)).scalar_one_or_none()
    if ch is None or ch.used_at is not None or ch.expires_at <= utcnow():
        return
    email, payload = None, json.loads(ch.payload) if ch.payload else None
    if payload:
        email = payload["email"]
    elif ch.user_id:
        u = session.get(User, ch.user_id)
        email = u.email if u and u.status == "active" else None
    if not email:
        return                                                            # decoy challenge: say nothing
    code = _new_code()
    session.execute(update(MfaChallenge).where(MfaChallenge.id == challenge_id).values(
        code_hash=_code_hash(challenge_id, code), attempts=0, expires_at=utcnow() + timedelta(minutes=cfg.OTP_TTL_MIN)))
    bg.add_task(mailer.send_email, email, "Your Risk Manager verification code", _code_mail(code, ch.purpose))


def _code_mail(code: str, purpose: str) -> str:
    what = {"signup": "finish creating your account", "login": "sign in", "admin_login": "sign in to the admin console"}[purpose]
    return (f"Your verification code to {what} is:\n\n    {code}\n\nIt expires in {cfg.OTP_TTL_MIN} minutes and works once.\n"
            "If you did not request this, ignore this email: nobody can sign in without this code. "
            "Never share it; Risk Manager staff will never ask for it.\n")


# ------------------------------------------------------------------ sign-up
def signup(session, bg, email_raw: str, password: str, full_name: str, ip: str) -> dict:
    try:
        email = identity.normalize_email(email_raw)
        name = identity.validate_full_name(full_name)
    except identity.InvalidIdentity as e:
        raise fail(422, str(e))
    problems = passwords.validate_password(password, email, name)
    if problems:
        raise fail(422, "Password " + "; ".join(problems))
    ratelimit.hit(session, f"signup:ip:{ip}", cfg.RL_SIGNUP_PER_IP)
    ratelimit.hit(session, f"signup:email:{email}", cfg.RL_SIGNUP_PER_EMAIL)
    pw_hash = passwords.hash_password(password)                            # always hashed: equal timing for new and existing emails
    existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        ch, _ = issue_challenge(session, None, "signup", ip, decoy=True)
        bg.add_task(mailer.send_email, email, "Sign-up attempt on your Risk Manager account",
                    "Someone tried to create a Risk Manager account with this email address.\n\n"
                    "If it was you, you already have an account: sign in, or use 'Forgot password'. If not, no action is needed.\n")
    else:
        ch, code = issue_challenge(session, None, "signup", ip, payload={"email": email, "name": name, "pw": pw_hash})
        bg.add_task(mailer.send_email, email, "Your Risk Manager verification code", _code_mail(code, "signup"))
    return {"challenge_id": ch.id, "expires_in": cfg.OTP_TTL_MIN * 60, "message": SIGNUP_MESSAGE}


def signup_verify(session, challenge_id: str, code: str, ip: str) -> User:
    ratelimit.hit(session, f"verify:ip:{ip}", cfg.RL_VERIFY_PER_IP)
    ch = check_challenge(session, challenge_id, code, "signup")
    if ch is None or not ch.payload:
        raise fail(400, GENERIC_CODE)
    data = json.loads(ch.payload)
    if session.execute(select(User.id).where(User.email == data["email"])).first():
        raise fail(400, GENERIC_CODE)
    user = User(email=data["email"], full_name=data["name"], password_hash=data["pw"], role="viewer", status="active", email_verified=True)
    session.add(user)
    session.flush()
    return user


# ------------------------------------------------------------------ sign-in (step 1: password + CAPTCHA, step 2: emailed code)
def login_step1(session, bg, email_raw: str, password: str, captcha_ok: bool, ip: str, admin: bool) -> dict:
    from app.auth import netutil
    email = light_email(email_raw)
    ratelimit.hit(session, f"login:ip:{ip}", cfg.RL_LOGIN_PER_IP)
    acct_key = f"login-fail:acct:{'admin:' if admin else ''}{email}"
    ratelimit.check(session, acct_key, cfg.RL_LOGIN_FAIL_PER_ACCOUNT)      # locked out (also for emails that do not exist)
    if not captcha_ok:
        raise fail(401, GENERIC_LOGIN)                                     # a CAPTCHA miss never counts against the account
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none() if email else None
    password_ok = passwords.verify_password(user.password_hash if user else None, password)
    eligible = bool(user and password_ok and user.status == "active" and user.email_verified and (user.role == "admin") == admin)
    if not eligible:
        ratelimit.record(session, acct_key)
        db.audit("anonymous", "ADMIN_LOGIN_FAILED" if admin else "LOGIN_FAILED", detail={"ip": ip}, session=session)
        raise fail(401, GENERIC_LOGIN)
    if admin and not netutil.ip_allowed(ip, cfg.ADMIN_ALLOWED_IPS):
        ratelimit.record(session, acct_key)
        db.audit(user.email, "ADMIN_LOGIN_BLOCKED_IP", detail={"ip": ip}, session=session)
        raise fail(401, GENERIC_LOGIN)
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    purpose = "admin_login" if admin else "login"
    ch, code = issue_challenge(session, user.id, purpose, ip)
    bg.add_task(mailer.send_email, user.email, "Your Risk Manager verification code", _code_mail(code, purpose))
    return {"challenge_id": ch.id, "mfa_required": True, "expires_in": cfg.OTP_TTL_MIN * 60,
            "message": "Password accepted. Enter the 6-digit code we emailed you."}


def login_step2(session, challenge_id: str, code: str, ip: str, user_agent: str, admin: bool) -> tuple[User, str, str, int, int, str]:
    from app.auth import netutil
    ratelimit.hit(session, f"verify:ip:{ip}", cfg.RL_VERIFY_PER_IP)
    ch = check_challenge(session, challenge_id, code, "admin_login" if admin else "login")
    user = session.get(User, ch.user_id) if ch and ch.user_id else None
    if not user or user.status != "active" or (user.role == "admin") != admin:
        raise fail(401, GENERIC_CODE)
    if admin and not netutil.ip_allowed(ip, cfg.ADMIN_ALLOWED_IPS):
        raise fail(401, GENERIC_CODE)
    ratelimit.clear(session, f"login-fail:acct:{'admin:' if admin else ''}{user.email}")
    user.last_login_at, user.last_login_ip = utcnow(), ip
    return (user, *create_session(session, user, admin, ip, user_agent))


# ------------------------------------------------------------------ sessions
def create_session(session, user: User, admin: bool, ip: str, user_agent: str) -> tuple[str, str, int, int, str]:
    max_age = timedelta(hours=cfg.ADMIN_SESSION_MAX_HOURS) if admin else timedelta(days=cfg.SESSION_MAX_DAYS)
    access_min = cfg.ADMIN_ACCESS_TTL_MIN if admin else cfg.ACCESS_TTL_MIN
    refresh_ttl = timedelta(hours=cfg.ADMIN_REFRESH_TTL_HOURS if admin else cfg.REFRESH_TTL_HOURS)
    sess = AuthSession(user_id=user.id, is_admin=admin, expires_at=utcnow() + max_age, ip=ip, user_agent=(user_agent or "")[:255])
    session.add(sess)
    session.flush()
    plain, h = tokens.new_refresh_token()
    session.add(RefreshToken(token_hash=h, session_id=sess.id, expires_at=min(utcnow() + refresh_ttl, sess.expires_at)))
    access = tokens.issue_access(user.id, user.role, sess.id, user.token_version, access_min)
    return access, plain, access_min * 60, int(refresh_ttl.total_seconds()), sess.id


def revoke_session(session, session_id: str) -> None:
    session.execute(update(AuthSession).where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))


def revoke_all_sessions(session, user_id: str) -> None:
    session.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))


def rotate_refresh(session, refresh_plain: str, csrf_header: str | None, ip: str, user_agent: str) -> tuple[User, str, str, int, int, str]:
    h = tokens.hash_token(refresh_plain)
    rt = session.get(RefreshToken, h)
    if rt is None:
        raise fail(401, "Session expired")
    sess = session.get(AuthSession, rt.session_id)
    if sess is None or sess.revoked_at is not None or sess.expires_at <= utcnow():
        raise fail(401, "Session expired")
    if not tokens.csrf_ok(sess.id, csrf_header):
        raise fail(403, "CSRF check failed")
    already_spent = rt.used_at is not None                                 # read BEFORE claiming: the ORM update below mutates `rt` in memory
    claimed = session.execute(update(RefreshToken).where(RefreshToken.token_hash == h, RefreshToken.used_at.is_(None))
                              .values(used_at=utcnow())).rowcount
    if claimed != 1 or already_spent:                                      # a spent token came back: assume it was stolen
        revoke_session(session, sess.id)
        db.audit("system", "REFRESH_REUSE_DETECTED", detail={"session": sess.id, "ip": ip}, session=session)
        session.commit()                                                   # keep the revocation even though we are about to raise
        raise fail(401, "Session expired")
    if rt.expires_at <= utcnow():
        raise fail(401, "Session expired")
    user = session.get(User, sess.user_id)
    if user is None or user.status != "active":
        raise fail(401, "Session expired")
    ttl = timedelta(hours=cfg.ADMIN_REFRESH_TTL_HOURS if sess.is_admin else cfg.REFRESH_TTL_HOURS)
    plain, nh = tokens.new_refresh_token()
    session.add(RefreshToken(token_hash=nh, session_id=sess.id, expires_at=min(utcnow() + ttl, sess.expires_at)))
    access_min = cfg.ADMIN_ACCESS_TTL_MIN if sess.is_admin else cfg.ACCESS_TTL_MIN
    access = tokens.issue_access(user.id, user.role, sess.id, user.token_version, access_min)
    return user, access, plain, access_min * 60, int(ttl.total_seconds()), sess.id


# ------------------------------------------------------------------ password reset / change
def forgot_password(session, bg, email_raw: str, captcha_ok: bool, ip: str) -> dict:
    ratelimit.hit(session, f"forgot:ip:{ip}", cfg.RL_FORGOT_PER_IP)
    if not captcha_ok:
        raise fail(400, "CAPTCHA incorrect or expired. Please try again.")   # says nothing about the account
    email = light_email(email_raw)
    if email:
        ratelimit.hit(session, f"forgot:email:{email}", cfg.RL_FORGOT_PER_EMAIL)
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none() if email else None
    if user and user.status == "active":
        session.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
                        .values(used_at=utcnow()))                          # older links die when a new one is requested
        token = pysecrets.token_urlsafe(32)                                # 256 bits
        session.add(PasswordResetToken(token_hash=tokens.hash_token(token), user_id=user.id,
                                       expires_at=utcnow() + timedelta(minutes=cfg.RESET_TOKEN_TTL_MIN)))
        # The link is built from configuration, never from the request's Host header (host-header poisoning), and the token
        # sits in the URL *fragment* so it is not sent to servers, proxies or Referer headers.
        link = f"{cfg.FRONTEND_URL}/#/reset?token={token}"
        bg.add_task(mailer.send_email, user.email, "Reset your Risk Manager password",
                    f"We received a request to reset your password.\n\nOpen this link within {cfg.RESET_TOKEN_TTL_MIN} minutes:\n\n{link}\n\n"
                    "It works once. If you did not ask for this, ignore this email: your password has not changed.\n")
    return {"message": RESET_MESSAGE}


def reset_password(session, bg, token: str, new_password: str, ip: str) -> None:
    ratelimit.hit(session, f"verify:ip:{ip}", cfg.RL_VERIFY_PER_IP)
    row = session.get(PasswordResetToken, tokens.hash_token(token))
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise fail(400, GENERIC_RESET)
    user = session.get(User, row.user_id)
    if user is None or user.status != "active":
        raise fail(400, GENERIC_RESET)
    problems = passwords.validate_password(new_password, user.email, user.full_name)
    if problems:
        raise fail(422, "Password " + "; ".join(problems))
    if passwords.verify_password(user.password_hash, new_password):
        raise fail(422, "Choose a password you have not used before")
    spent = session.execute(update(PasswordResetToken).where(PasswordResetToken.token_hash == row.token_hash, PasswordResetToken.used_at.is_(None))
                            .values(used_at=utcnow())).rowcount
    if spent != 1:
        raise fail(400, GENERIC_RESET)
    _set_password(session, user, new_password)
    bg.add_task(mailer.send_email, user.email, "Your Risk Manager password was changed",
                "Your password was just changed and you have been signed out everywhere.\n"
                "If this was not you, reset your password again immediately and contact your administrator.\n")
    db.audit(user.email, "PASSWORD_RESET", session=session)


def _set_password(session, user: User, new_password: str) -> None:
    user.password_hash = passwords.hash_password(new_password)
    user.password_changed_at = utcnow()
    user.token_version += 1                                                # every outstanding access token dies now
    revoke_all_sessions(session, user.id)
    session.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
                    .values(used_at=utcnow()))


def change_password(session, bg, user: User, current: str, new_password: str) -> None:
    if not passwords.verify_password(user.password_hash, current):
        raise fail(403, "Current password is incorrect")
    problems = passwords.validate_password(new_password, user.email, user.full_name)
    if problems:
        raise fail(422, "Password " + "; ".join(problems))
    if passwords.verify_password(user.password_hash, new_password):
        raise fail(422, "Choose a password you have not used before")
    _set_password(session, user, new_password)
    bg.add_task(mailer.send_email, user.email, "Your Risk Manager password was changed",
                "Your password was just changed and you have been signed out everywhere.\n")
    db.audit(user.email, "PASSWORD_CHANGED", session=session)


# ------------------------------------------------------------------ admin bootstrap
def create_admin(session, email_raw: str, password: str, full_name: str = "Administrator") -> User:
    email = identity.normalize_email(email_raw)
    name = identity.validate_full_name(full_name)
    problems = passwords.validate_password(password, email, name)
    if problems:
        raise ValueError("Password " + "; ".join(problems))
    if session.execute(select(User.id).where(User.email == email)).first():
        raise ValueError("A user with that email already exists")
    u = User(email=email, full_name=name, password_hash=passwords.hash_password(password), role="admin", status="active", email_verified=True)
    session.add(u)
    session.flush()
    return u
