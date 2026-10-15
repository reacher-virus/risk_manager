"""Shared helpers for auth tests: a fresh cookie jar per client, CAPTCHA solving, reading emailed codes."""
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import mailer
from app.auth.models import User
from app.core import db

PW = "Tr1cky-Horse-Battery!"
ADMIN_PW = "Vault-Keeper-9-Lantern!"
CAPTCHA_TEXT = "KMPRT"


def new_client(base_url: str = "http://testserver") -> TestClient:
    from app.api.main import app
    return TestClient(app, base_url=base_url)        # no lifespan: the session fixture already loaded the app state


def uniq(prefix: str = "u") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}@example.org"


def cap(c) -> dict:
    r = c.get("/auth/captcha")
    assert r.status_code == 200, r.text
    return {"captcha_id": r.json()["captcha_id"], "captcha_answer": CAPTCHA_TEXT}


def last_code(to: str) -> str:
    for m in reversed(mailer.OUTBOX):
        if m["to"] == to:
            hit = re.search(r"\n\s{4}(\d{6})\n", m["body"])
            if hit:
                return hit.group(1)
    raise AssertionError(f"no code emailed to {to}")


def last_mail(to: str, subject_contains: str = "") -> dict:
    for m in reversed(mailer.OUTBOX):
        if m["to"] == to and subject_contains in m["subject"]:
            return m
    raise AssertionError(f"no mail to {to} ({subject_contains})")


def signup(c, email, pw=PW, name="Ana Roy", verify=True):
    r = c.post("/auth/signup", json={"email": email, "password": pw, "full_name": name, **cap(c)})
    if not verify or r.status_code != 202:
        return r
    return c.post("/auth/signup/verify", json={"challenge_id": r.json()["challenge_id"], "code": last_code(email)})


def login(c, email, pw=PW, admin=False):
    base = "/auth/admin" if admin else "/auth"
    r = c.post(f"{base}/login", json={"email": email, "password": pw, **cap(c)})
    if r.status_code != 200:
        return r
    return c.post(f"{base}/login/verify", json={"challenge_id": r.json()["challenge_id"], "code": last_code(email)})


def set_role(email: str, role: str) -> None:
    with db.session_scope() as s:
        s.execute(select(User).where(User.email == email)).scalar_one().role = role


def make_user(role: str = "viewer", pw: str = PW):
    """Sign up + verify + (optionally) promote, then sign in on a fresh client. Returns (client, email)."""
    c, email = new_client(), uniq()
    assert signup(c, email, pw).status_code == 200
    if role != "viewer":
        set_role(email, role)
    assert login(c, email, pw).status_code == 200
    return c, email


def make_admin():
    from app.auth import service
    email = uniq("adm")
    with db.session_scope() as s:
        service.create_admin(s, email, ADMIN_PW)
    c = new_client()
    assert login(c, email, ADMIN_PW, admin=True).status_code == 200
    return c, email


def csrf(c) -> dict:
    return {"X-CSRF-Token": c.cookies.get("risk_csrf")}
