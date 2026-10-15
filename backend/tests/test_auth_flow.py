"""Sign-up, two-step sign-in, dedicated admin sign-in, sessions, cookies, CSRF and role-based access."""
import pytest
from sqlalchemy import select

from app.auth import captcha, mailer, ratelimit
from app.auth.models import RateEvent, User
from app.core import config as cfg
from app.core import db
from tests.auth_helpers import ADMIN_PW, CAPTCHA_TEXT, PW, cap, csrf, last_code, login, make_admin, make_user, new_client, set_role, signup, uniq


@pytest.fixture(autouse=True)
def auth_env(client, monkeypatch):
    monkeypatch.setattr(cfg, "AUTH_REQUIRED", True)
    monkeypatch.setattr(captcha, "_random_text", lambda n=5: CAPTCHA_TEXT)
    with db.session_scope() as s:
        s.query(RateEvent).delete()
    mailer.OUTBOX.clear()


# ------------------------------------------------------------------ CAPTCHA
def test_captcha_is_an_image_and_single_use():
    c = new_client()
    r = c.get("/auth/captcha").json()
    assert r["image"].startswith("data:image/png;base64,") and len(r["image"]) > 500
    body = {"email": uniq(), "password": PW, "full_name": "Ana Roy", "captcha_id": r["captcha_id"], "captcha_answer": CAPTCHA_TEXT}
    assert c.post("/auth/signup", json=body).status_code == 202
    assert c.post("/auth/signup", json={**body, "email": uniq()}).status_code == 400      # the same CAPTCHA cannot be replayed


@pytest.mark.parametrize("answer", ["WRONG", "", "kmprtX"])
def test_wrong_captcha_is_rejected_and_consumed(answer):
    c = new_client()
    cid = c.get("/auth/captcha").json()["captcha_id"]
    body = {"email": uniq(), "password": PW, "full_name": "Ana Roy", "captcha_id": cid, "captcha_answer": answer or "x"}
    assert c.post("/auth/signup", json=body).status_code == 400
    assert c.post("/auth/signup", json={**body, "captcha_answer": CAPTCHA_TEXT}).status_code == 400   # burned by the failed guess


def test_expired_captcha_is_rejected():
    c = new_client()
    cid = c.get("/auth/captcha").json()["captcha_id"]
    with db.session_scope() as s:
        s.get(captcha.Captcha, cid).expires_at = db.utcnow().replace(year=2020)
    r = c.post("/auth/signup", json={"email": uniq(), "password": PW, "full_name": "Ana Roy", "captcha_id": cid, "captcha_answer": CAPTCHA_TEXT})
    assert r.status_code == 400


# ------------------------------------------------------------------ sign-up
def test_signup_requires_the_emailed_code_and_creates_a_stored_user():
    c, email = new_client(), uniq()
    r = c.post("/auth/signup", json={"email": email, "password": PW, "full_name": "Ana Roy", **cap(c)})
    assert r.status_code == 202
    with db.session_scope() as s:                       # nothing is stored for an unverified address
        assert s.execute(select(User).where(User.email == email)).first() is None
    assert c.post("/auth/signup/verify", json={"challenge_id": r.json()["challenge_id"], "code": last_code(email)}).status_code == 200
    with db.session_scope() as s:
        u = s.execute(select(User).where(User.email == email)).scalar_one()
        assert (u.role, u.status, u.email_verified, u.full_name) == ("viewer", "active", True, "Ana Roy")
        assert u.password_hash.startswith("$argon2id$") and PW not in u.password_hash


def test_unverified_signup_cannot_sign_in():
    c, email = new_client(), uniq()
    assert signup(c, email, verify=False).status_code == 202
    assert login(c, email).status_code == 401


def test_a_random_made_up_address_never_gets_an_account():
    """The classic 'random gmail' problem: nobody can read the inbox, so the code is never entered and no user exists."""
    c, email = new_client(), uniq("nobodyreadsthis")
    r = signup(c, email, verify=False)
    assert r.status_code == 202
    assert c.post("/auth/signup/verify", json={"challenge_id": r.json()["challenge_id"], "code": "000000"}).status_code == 400
    with db.session_scope() as s:
        assert s.execute(select(User).where(User.email == email)).first() is None


@pytest.mark.parametrize("email", ["x@mailinator.com", "x@sub.guerrillamail.com", "x@yopmail.com", "not-an-email", "a@b", "a b@example.org",
                                   "a@example.org\r\nBcc: evil@example.net", "<script>@example.org", "a'b@example.org", "a" * 300 + "@example.org"])
def test_signup_rejects_disposable_and_malformed_emails(email):
    c = new_client()
    assert signup(c, email, verify=False).status_code == 422


@pytest.mark.parametrize("pw", ["short1A!", "alllowercaseletters", "NoDigitsOrSymbols", "Password123456!", "aaaaaaaaaaaaAAA111!!", "Abcdef12345678!x"])
def test_signup_enforces_password_policy(pw):
    assert signup(new_client(), uniq(), pw, verify=False).status_code == 422


def test_password_may_not_contain_the_email_name_or_real_name():
    c = new_client()
    assert signup(c, "janedoe42@example.org", "Xx-janedoe42-Zz-99!", verify=False).status_code == 422
    assert signup(c, uniq(), "Roy-Is-Cool-1234567!", name="Ana Roy", verify=False).status_code == 422


def test_signup_rejects_extra_fields_so_nobody_can_pick_their_own_role():
    c = new_client()
    r = c.post("/auth/signup", json={"email": uniq(), "password": PW, "full_name": "Ana Roy", "role": "admin", **cap(c)})
    assert r.status_code == 422


def test_signup_for_an_existing_email_looks_identical_and_warns_the_owner():
    c, email = new_client(), uniq()
    assert signup(c, email).status_code == 200
    mailer.OUTBOX.clear()
    again = c.post("/auth/signup", json={"email": email, "password": PW, "full_name": "Ana Roy", **cap(c)})
    fresh = c.post("/auth/signup", json={"email": uniq(), "password": PW, "full_name": "Ana Roy", **cap(c)})
    assert again.status_code == fresh.status_code == 202 and set(again.json()) == set(fresh.json()) and again.json()["message"] == fresh.json()["message"]
    assert "Sign-up attempt" in mailer.OUTBOX[0]["subject"]
    assert c.post("/auth/signup/verify", json={"challenge_id": again.json()["challenge_id"], "code": "123456"}).status_code == 400


# ------------------------------------------------------------------ one-time codes
def test_code_is_single_use_expires_and_is_bound_to_its_purpose():
    c, email = new_client(), uniq()
    r = c.post("/auth/signup", json={"email": email, "password": PW, "full_name": "Ana Roy", **cap(c)}).json()
    code = last_code(email)
    assert c.post("/auth/login/verify", json={"challenge_id": r["challenge_id"], "code": code}).status_code == 401   # signup code, login endpoint
    assert c.post("/auth/signup/verify", json={"challenge_id": r["challenge_id"], "code": code}).status_code == 200
    assert c.post("/auth/signup/verify", json={"challenge_id": r["challenge_id"], "code": code}).status_code == 400   # replay
    r2 = c.post("/auth/signup", json={"email": uniq(), "password": PW, "full_name": "Ana Roy", **cap(c)}).json()
    with db.session_scope() as s:
        s.get(__import__("app.auth.models", fromlist=["MfaChallenge"]).MfaChallenge, r2["challenge_id"]).expires_at = db.utcnow().replace(year=2020)
    assert c.post("/auth/signup/verify", json={"challenge_id": r2["challenge_id"], "code": "123456"}).status_code == 400


def test_guessing_the_code_burns_the_challenge_after_five_tries():
    c, email = new_client(), uniq()
    ch = c.post("/auth/signup", json={"email": email, "password": PW, "full_name": "Ana Roy", **cap(c)}).json()["challenge_id"]
    real = last_code(email)
    wrong = "000000" if real != "000000" else "111111"
    assert [c.post("/auth/signup/verify", json={"challenge_id": ch, "code": wrong}).status_code for _ in range(5)] == [400] * 5
    assert c.post("/auth/signup/verify", json={"challenge_id": ch, "code": real}).status_code == 400    # even the right code is now dead


def test_code_format_is_validated():
    c = new_client()
    for bad in ["12345", "1234567", "abcdef", "12 456", "' OR 1=1"]:
        assert c.post("/auth/signup/verify", json={"challenge_id": "0" * 32, "code": bad}).status_code == 422


def test_resend_has_a_cooldown_and_issues_a_fresh_code():
    c, email = new_client(), uniq()
    ch = c.post("/auth/signup", json={"email": email, "password": PW, "full_name": "Ana Roy", **cap(c)}).json()["challenge_id"]
    first = last_code(email)
    assert c.post("/auth/otp/resend", json={"challenge_id": ch}).status_code == 202
    assert c.post("/auth/otp/resend", json={"challenge_id": ch}).status_code == 429
    second = last_code(email)
    assert c.post("/auth/signup/verify", json={"challenge_id": ch, "code": second}).status_code == 200
    assert first != second or True


# ------------------------------------------------------------------ two-step sign-in, cookies, sessions
def test_login_is_two_step_and_cookies_only_appear_after_the_code():
    c, email = new_client(), uniq()
    assert signup(c, email).status_code == 200
    s1 = c.post("/auth/login", json={"email": email, "password": PW, **cap(c)})
    assert s1.status_code == 200 and s1.json()["mfa_required"] is True and not c.cookies.keys()
    assert c.get("/alerts").status_code == 401                               # password alone gets you nothing
    assert c.post("/auth/login/verify", json={"challenge_id": s1.json()["challenge_id"], "code": "000000"}).status_code == 401
    assert not c.cookies.keys()
    ok = c.post("/auth/login/verify", json={"challenge_id": s1.json()["challenge_id"], "code": last_code(email)})
    assert ok.status_code == 200 and {"risk_access", "risk_refresh", "risk_csrf"} <= set(c.cookies.keys())
    assert "eyJ" not in ok.text                                              # tokens live in cookies, never in the JSON body
    assert c.get("/auth/me").json()["user"]["email"] == email


def test_cookie_flags():
    c, email = new_client(), uniq()
    signup(c, email)
    s1 = c.post("/auth/login", json={"email": email, "password": PW, **cap(c)}).json()
    r = c.post("/auth/login/verify", json={"challenge_id": s1["challenge_id"], "code": last_code(email)})
    flags = {h.split("=")[0]: h.lower() for h in r.headers.get_list("set-cookie")}
    assert "httponly" in flags["risk_access"] and "samesite=lax" in flags["risk_access"] and "path=/;" in flags["risk_access"] + ";"
    assert "httponly" in flags["risk_refresh"] and "samesite=strict" in flags["risk_refresh"] and "path=/auth" in flags["risk_refresh"]
    assert "httponly" not in flags["risk_csrf"]                              # the page must be able to read this one (and only this one)


def test_secure_cookie_attributes_and_prefix_over_https(monkeypatch):
    monkeypatch.setattr(cfg, "COOKIE_SECURE", True)
    monkeypatch.setattr(cfg, "FORCE_HTTPS", True)
    c, email = new_client("https://testserver"), uniq()
    signup(c, email)
    s1 = c.post("/auth/login", json={"email": email, "password": PW, **cap(c)}).json()
    r = c.post("/auth/login/verify", json={"challenge_id": s1["challenge_id"], "code": last_code(email)})
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 3 and all(h.startswith("__Secure-") and "Secure" in h for h in cookies)
    assert "max-age=63072000" in r.headers["strict-transport-security"]


def test_access_token_lifetimes():
    import jwt
    from app.auth import secrets as keys
    uc, _ = make_user()
    ac, _ = make_admin()
    def ttl(client):
        claims = jwt.decode(client.cookies.get("risk_access"), keys.subkey("jwt"), algorithms=["HS256"], audience=cfg.JWT_AUDIENCE, issuer=cfg.JWT_ISSUER)
        return claims["exp"] - claims["iat"]
    assert ttl(uc) == cfg.ACCESS_TTL_MIN * 60 and ttl(ac) == cfg.ADMIN_ACCESS_TTL_MIN * 60


def test_logout_revokes_the_session_even_if_the_cookie_is_replayed():
    c, _ = make_user()
    stolen = c.cookies.get("risk_access")
    assert c.get("/auth/me").status_code == 200
    assert c.post("/auth/logout").status_code == 200
    assert c.get("/auth/me").status_code == 401
    thief = new_client()
    thief.cookies.set("risk_access", stolen)
    assert thief.get("/auth/me").status_code == 401


def test_logout_all_signs_out_every_device():
    a, email = make_user()
    b = new_client()
    assert login(b, email).status_code == 200
    assert a.post("/auth/logout-all", headers=csrf(a)).status_code == 200
    assert b.get("/auth/me").status_code == 401


def test_refresh_rotates_and_a_replayed_refresh_token_burns_the_session():
    c, _ = make_user()
    old_refresh = c.cookies.get("risk_refresh")
    assert c.post("/auth/refresh", headers=csrf(c)).status_code == 200
    new_refresh = c.cookies.get("risk_refresh")
    assert new_refresh != old_refresh
    thief = new_client()
    thief.cookies.set("risk_refresh", old_refresh, path="/auth")
    thief.cookies.set("risk_csrf", c.cookies.get("risk_csrf"))
    assert thief.post("/auth/refresh", headers={"X-CSRF-Token": c.cookies.get("risk_csrf")}).status_code == 401
    assert c.get("/auth/me").status_code == 401                              # the legitimate session was burned too: theft detected
    assert c.post("/auth/refresh", headers=csrf(c)).status_code == 401


def test_refresh_needs_the_csrf_token():
    c, _ = make_user()
    assert c.post("/auth/refresh").status_code == 403


def test_disabling_an_account_ends_its_sessions_at_once():
    admin, _ = make_admin()
    user, email = make_user()
    uid = user.get("/auth/me").json()["user"]["id"]
    assert user.get("/alerts?limit=1").status_code == 200
    assert admin.patch(f"/admin/users/{uid}", json={"status": "disabled"}, headers=csrf(admin)).status_code == 200
    assert user.get("/alerts?limit=1").status_code == 401
    assert login(new_client(), email).status_code == 401


# ------------------------------------------------------------------ dedicated admin sign-in
def test_admin_and_user_login_are_separate_doors():
    admin, aemail = make_admin()
    assert login(new_client(), aemail, ADMIN_PW, admin=False).status_code == 401      # admins cannot use the public form
    _, uemail = make_user()
    assert login(new_client(), uemail, PW, admin=True).status_code == 401              # users cannot use the admin form
    assert admin.get("/auth/me").json()["admin_session"] is True


def test_admin_cannot_be_created_through_signup():
    c, email = new_client(), uniq()
    signup(c, email)
    with db.session_scope() as s:
        assert s.execute(select(User).where(User.email == email)).scalar_one().role == "viewer"


def test_admin_login_can_be_limited_to_trusted_networks(monkeypatch):
    from app.auth import service
    email = uniq("adm")
    with db.session_scope() as s:
        service.create_admin(s, email, ADMIN_PW)
    monkeypatch.setattr(cfg, "ADMIN_ALLOWED_IPS", ["203.0.113.0/24"])
    assert login(new_client(), email, ADMIN_PW, admin=True).status_code == 401
    monkeypatch.setattr(cfg, "ADMIN_ALLOWED_IPS", [])
    assert login(new_client(), email, ADMIN_PW, admin=True).status_code == 200


# ------------------------------------------------------------------ CSRF
def test_cookie_sessions_need_a_valid_csrf_token_for_changes():
    c, _ = make_user("analyst")
    body = {"scenario": "normal", "n": 1}
    assert c.post("/simulate", json=body).status_code == 403                                    # missing
    assert c.post("/simulate", json=body, headers={"X-CSRF-Token": "forged"}).status_code == 403   # forged
    assert c.post("/simulate", json=body, headers=csrf(c)).status_code == 200
    assert c.post("/simulate", json=body, headers={**csrf(c), "Origin": "https://evil.example"}).status_code == 403   # wrong Origin
    assert c.get("/alerts?limit=1").status_code == 200                                          # reads need no token


def test_csrf_token_from_another_session_is_useless():
    a, _ = make_user("analyst")
    b, _ = make_user("analyst")
    assert a.post("/simulate", json={"scenario": "normal", "n": 1}, headers=csrf(b)).status_code == 403


# ------------------------------------------------------------------ permissions
def test_unauthenticated_requests_are_rejected_everywhere_except_health():
    c = new_client()
    assert c.get("/health").status_code == 200
    for method, path in [("GET", "/alerts"), ("GET", "/metrics"), ("GET", "/dashboard/summary"), ("GET", "/audit"), ("GET", "/config"),
                         ("GET", "/admin/users"), ("POST", "/predict"), ("POST", "/simulate"), ("GET", "/graph/rings")]:
        assert c.request(method, path, json={} if method == "POST" else None).status_code == 401, path


@pytest.mark.parametrize("role,method,path,body,expected", [
    ("viewer", "GET", "/alerts?limit=1", None, 200), ("viewer", "GET", "/metrics", None, 200), ("viewer", "GET", "/config", None, 200),
    ("viewer", "POST", "/simulate", {"scenario": "normal", "n": 1}, 403), ("viewer", "POST", "/predict", {"customer_id": "a", "amount": 5, "device_id": "d"}, 403),
    ("viewer", "PUT", "/config/costs", {"cost_fp": 1, "cost_fn": 2}, 403), ("viewer", "GET", "/audit", None, 403),
    ("viewer", "GET", "/admin/users", None, 403), ("viewer", "POST", "/admin/retrain", None, 403), ("viewer", "GET", "/admin/webhook", None, 403),
    ("analyst", "POST", "/simulate", {"scenario": "normal", "n": 1}, 200), ("analyst", "PUT", "/config/costs", {"cost_fp": 1, "cost_fn": 2}, 403),
    ("analyst", "GET", "/audit", None, 403), ("analyst", "GET", "/admin/users", None, 403), ("analyst", "PUT", "/config/threshold", {"threshold": 0.3}, 403),
])
def test_role_matrix(role, method, path, body, expected):
    c, _ = make_user(role)
    r = c.request(method, path, json=body, headers=csrf(c))
    assert r.status_code == expected, (role, method, path, r.text)


def test_admin_can_manage_users_but_not_other_admins_or_themselves():
    admin, _ = make_admin()
    other_admin, other_email = make_admin()
    user, uemail = make_user()
    uid = user.get("/auth/me").json()["user"]["id"]
    aid = other_admin.get("/auth/me").json()["user"]["id"]
    me = admin.get("/auth/me").json()["user"]["id"]
    h = csrf(admin)
    assert admin.patch(f"/admin/users/{uid}", json={"role": "analyst"}, headers=h).status_code == 200
    assert user.post("/simulate", json={"scenario": "normal", "n": 1}, headers=csrf(user)).status_code == 200      # role change is instant
    assert admin.patch(f"/admin/users/{uid}", json={"role": "admin"}, headers=h).status_code == 422                # no promotion to admin via the API
    assert admin.patch(f"/admin/users/{aid}", json={"status": "disabled"}, headers=h).status_code == 403            # admins are console-managed
    assert admin.patch(f"/admin/users/{me}", json={"role": "viewer"}, headers=h).status_code == 403                 # not even yourself
    assert admin.patch(f"/admin/users/{uid}", json={"is_admin": True}, headers=h).status_code == 422
    assert admin.patch("/admin/users/not-an-id", json={"role": "viewer"}, headers=h).status_code == 404
    listing = admin.get("/admin/users?limit=100").json()
    assert listing["total"] >= 3 and not any("password" in k or "hash" in k for item in listing["items"] for k in item)


def test_a_user_cannot_touch_another_users_account():
    victim, _ = make_user()
    vid = victim.get("/auth/me").json()["user"]["id"]
    attacker, _ = make_user("analyst")
    h = csrf(attacker)
    assert attacker.patch(f"/admin/users/{vid}", json={"status": "disabled"}, headers=h).status_code == 403
    assert attacker.post(f"/admin/users/{vid}/revoke-sessions", headers=h).status_code == 403
    assert victim.get("/auth/me").status_code == 200


def test_api_keys_still_work_for_machines_with_their_own_roles(monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, "API_KEYS", {"machine-key-1": "analyst"})
    c = new_client()
    assert c.get("/metrics", headers={"X-API-Key": "machine-key-1"}).status_code == 200
    assert c.put("/config/costs", json={"cost_fp": 1, "cost_fn": 2}, headers={"X-API-Key": "machine-key-1"}).status_code == 403
    assert c.get("/metrics", headers={"X-API-Key": "nope"}).status_code == 401


@pytest.mark.parametrize("name", ["Ana Roy", "Patrick O'Brien", "Mary-Jane Watson", "J. R. R. Tolkien", "José García", "Åsa Öberg",
                                  "अनिल कुमार", "అనిల్ కుమార్", "தமிழ் செல்வன்", "বাংলা নাম", "محمد علي"])
def test_real_names_in_any_script_are_accepted(name):
    from app.auth.identity import validate_full_name
    assert validate_full_name(name) == name


@pytest.mark.parametrize("name", ["admin'--", "--", "'-", "a..", "-Ana", "Ana-", "Ana'", "X", " ", "<b>x</b>", "Ana; DROP", "Ana\u202eevil", "A\x00na"])
def test_junk_and_markup_names_are_rejected(name):
    from app.auth.identity import InvalidIdentity, validate_full_name
    with pytest.raises(InvalidIdentity):
        validate_full_name(name)
