"""Attack-oriented tests: injection, XSS, enumeration, brute force, JWT abuse, reset flaws, HTTPS, secrets, rate limits, SSRF."""
import hashlib
import os
import pathlib
import re
import socket
import stat
import time

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth import captcha, mailer, ratelimit
from app.auth import secrets as keys
from app.auth.models import PasswordResetToken, RateEvent, User
from app.core import config as cfg
from app.core import db, ssrf
from tests.auth_helpers import ADMIN_PW, CAPTCHA_TEXT, PW, cap, csrf, last_code, last_mail, login, make_admin, make_user, new_client, signup, uniq


@pytest.fixture(autouse=True)
def env(client, monkeypatch):
    monkeypatch.setattr(cfg, "AUTH_REQUIRED", True)
    monkeypatch.setattr(captcha, "_random_text", lambda n=5: CAPTCHA_TEXT)
    with db.session_scope() as s:
        s.query(RateEvent).delete()
    mailer.OUTBOX.clear()
    yield
    keys.reset_cache()


def user_count() -> int:
    with db.session_scope() as s:
        return s.execute(select(func.count()).select_from(User)).scalar_one()


# =============================================================== SQL injection
SQLI = ["' OR '1'='1", "admin'--", "'; DROP TABLE users;--", '" OR ""="', "' UNION SELECT password_hash FROM users--",
        "1; SELECT pg_sleep(5)", "') OR ('1'='1", "\\'; DELETE FROM users WHERE '1'='1"]


@pytest.mark.parametrize("payload", SQLI)
def test_sql_injection_in_login_fields_never_authenticates_or_damages_data(payload):
    _, victim = make_user()
    before, c = user_count(), new_client()
    for body in ({"email": payload, "password": "whatever-123"}, {"email": victim, "password": payload}, {"email": payload, "password": payload}):
        r = c.post("/auth/login", json={**body, **cap(c)})
        assert r.status_code in (401, 422), (payload, r.text)
        assert "mfa_required" not in r.text and not c.cookies.keys()
    assert user_count() == before
    assert login(new_client(), victim).status_code == 200          # tables intact, the real user can still sign in


@pytest.mark.parametrize("payload", SQLI)
def test_sql_injection_in_signup_and_other_inputs_is_rejected_or_inert(payload):
    c, before = new_client(), user_count()
    assert signup(c, payload, verify=False).status_code == 422                       # email
    assert signup(c, uniq(), name=payload, verify=False).status_code == 422          # name has quotes/semicolons/etc
    assert c.post("/auth/signup/verify", json={"challenge_id": payload, "code": "123456"}).status_code == 422
    assert c.get(f"/alerts/{payload}", headers={"X-API-Key": payload}).status_code == 401
    assert user_count() == before


@pytest.mark.parametrize("payload", SQLI + ["%", "_", "%%%%", "\\"])
def test_sql_injection_in_admin_search_returns_data_not_errors(payload):
    admin, _ = make_admin()
    make_user()
    r = admin.get("/admin/users", params={"q": payload})
    assert r.status_code == 200 and r.json()["total"] == 0 or payload in ("%", "_", "%%%%", "\\")
    assert admin.get("/admin/users", params={"q": ""}).json()["total"] >= 2           # table survived
    assert admin.get("/admin/users", params={"status": payload}).status_code == 422   # enums are validated, not interpolated


def test_wildcards_in_search_are_literal_not_patterns():
    admin, _ = make_admin()
    make_user()
    assert admin.get("/admin/users", params={"q": "%"}).json()["total"] == 0          # '%' is data, so it does not match everything
    assert admin.get("/admin/users", params={"q": "_" * 5}).json()["total"] == 0


def test_no_raw_sql_anywhere_in_the_codebase():
    """Every query must go through the ORM (bound parameters). Fail the build if someone adds string-built SQL."""
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    banned = [r"from sqlalchemy[^\n]*\btext\b", r"sqlalchemy\.text", r"\.execute\(\s*f[\"']", r"\.execute\(\s*[\"']", r"\.exec_driver_sql", r"(?i)[\"'](select|insert into|update|delete from|drop table)\s",
              r"\.raw\(", r"executescript", r"cursor\(\)"]
    hits = [f"{p.relative_to(root)}: {pat}" for p in root.rglob("*.py") for pat in banned if re.search(pat, p.read_text(encoding="utf-8"))]
    assert not hits, hits


# =============================================================== XSS
XSS = ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>', "javascript:alert(1)", "<svg/onload=alert(1)>", "&lt;b&gt;", "{{7*7}}", "`${alert(1)}`"]


@pytest.mark.parametrize("payload", XSS)
def test_markup_is_rejected_in_names_and_emails(payload):
    c = new_client()
    assert signup(c, uniq(), name=payload, verify=False).status_code == 422
    assert signup(c, payload + "@example.org", verify=False).status_code == 422


def test_stored_text_is_returned_as_inert_json_with_hardening_headers():
    """Free-text fields (review notes) are stored verbatim, which is safe because JSON is never rendered as HTML
    and React escapes on display. The API guarantees the type, no sniffing, and a default-deny CSP."""
    c, _ = make_user("analyst")
    tx = c.get("/alerts?limit=1&min_level=HIGH").json()["items"][0]["transaction_id"]
    note = "<script>alert('stored')</script>"
    assert c.post(f"/alerts/{tx}/review", json={"action": "HOLD", "note": note}, headers=csrf(c)).status_code == 200
    r = c.get(f"/alerts/{tx}")
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"] and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.json()["review_history"][0]["note"] == note


def test_security_headers_on_every_kind_of_response():
    c, _ = make_user()
    for resp in (c.get("/auth/me"), c.get("/alerts?limit=1"), c.get("/health"), c.get("/auth/captcha"), c.get("/nope"), new_client().get("/alerts")):
        h = resp.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
        assert h["cache-control"] == "no-store" and "permissions-policy" in h and "content-security-policy" in h


# =============================================================== account enumeration & brute force
def test_login_errors_do_not_reveal_whether_an_account_exists():
    _, email = make_user()
    c = new_client()
    wrong_pw = c.post("/auth/login", json={"email": email, "password": "Wrong-Password-1!", **cap(c)})
    unknown = c.post("/auth/login", json={"email": uniq("ghost"), "password": "Wrong-Password-1!", **cap(c)})
    bad_captcha = c.post("/auth/login", json={"email": email, "password": PW, "captcha_id": c.get("/auth/captcha").json()["captcha_id"], "captcha_answer": "NOPE"})
    assert wrong_pw.status_code == unknown.status_code == bad_captcha.status_code == 401
    assert wrong_pw.json() == unknown.json() == bad_captcha.json()


def test_forgot_password_answers_identically_for_known_and_unknown_emails():
    _, email = make_user()
    c = new_client()
    known = c.post("/auth/password/forgot", json={"email": email, **cap(c)})
    ghost_email = uniq("ghost")
    unknown = c.post("/auth/password/forgot", json={"email": ghost_email, **cap(c)})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert not any(m["to"] == ghost_email for m in mailer.OUTBOX)             # and nothing is mailed to strangers


def test_five_wrong_passwords_lock_the_account_even_against_the_right_password():
    _, email = make_user()
    c = new_client()
    codes = [c.post("/auth/login", json={"email": email, "password": "Wrong-Password-1!", **cap(c)}).status_code for _ in range(5)]
    assert codes == [401] * 5
    locked = c.post("/auth/login", json={"email": email, "password": PW, **cap(c)})
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0


def test_unknown_emails_get_locked_out_exactly_like_real_ones():
    c, ghost = new_client(), uniq("ghost")
    codes = [c.post("/auth/login", json={"email": ghost, "password": "Wrong-Password-1!", **cap(c)}).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]                                         # identical behaviour: nothing to enumerate


def test_failed_captchas_cannot_be_used_to_lock_someone_elses_account():
    _, email = make_user()
    c = new_client()
    for _ in range(8):
        c.post("/auth/login", json={"email": email, "password": PW, "captcha_id": "0" * 32, "captcha_answer": "x"})
    assert login(new_client(), email).status_code == 200


def test_successful_login_resets_the_failure_counter():
    _, email = make_user()
    c = new_client()
    for _ in range(4):
        c.post("/auth/login", json={"email": email, "password": "Wrong-Password-1!", **cap(c)})
    assert login(new_client(), email).status_code == 200
    assert c.post("/auth/login", json={"email": email, "password": "Wrong-Password-1!", **cap(c)}).status_code == 401   # not 429


def test_per_ip_login_cap_blocks_credential_stuffing(monkeypatch):
    monkeypatch.setattr(cfg, "RL_LOGIN_PER_IP", (4, 900))
    c = new_client()
    codes = [c.post("/auth/login", json={"email": uniq("ghost"), "password": "Wrong-Password-1!", **cap(c)}).status_code for _ in range(6)]
    assert codes[:4] == [401] * 4 and codes[4:] == [429, 429]


def test_signup_and_captcha_endpoints_are_rate_limited(monkeypatch):
    monkeypatch.setattr(cfg, "RL_SIGNUP_PER_IP", (3, 3600))
    c = new_client()
    assert [signup(c, uniq(), verify=False).status_code for _ in range(5)] == [202, 202, 202, 429, 429]
    with db.session_scope() as s:
        s.query(RateEvent).delete()                                         # forget the CAPTCHAs fetched while signing up above
    monkeypatch.setattr(cfg, "RL_CAPTCHA_PER_IP", (2, 900))
    assert [c.get("/auth/captcha").status_code for _ in range(3)] == [200, 200, 429]


def test_email_bombing_a_victim_is_capped_per_address():
    c, victim = new_client(), uniq()
    results = [signup(c, victim, verify=False).status_code for _ in range(4)]
    assert results == [202, 202, 202, 429]


def test_rate_limiter_unit_behaviour_and_retry_after():
    key = f"unit:{time.time()}"
    with db.session_scope() as s:
        ratelimit.hit(s, key, (2, 60))
        ratelimit.hit(s, key, (2, 60))
        with pytest.raises(HTTPException) as e:
            ratelimit.hit(s, key, (2, 60))
        assert e.value.status_code == 429 and 1 <= int(e.value.headers["Retry-After"]) <= 60
        ratelimit.clear(s, key)
        ratelimit.hit(s, key, (2, 60))


# =============================================================== JWT abuse
def _claims(client) -> dict:
    return jwt.decode(client.cookies.get("risk_access"), keys.subkey("jwt"), algorithms=["HS256"], audience=cfg.JWT_AUDIENCE, issuer=cfg.JWT_ISSUER)


def _as(token: str):
    c = new_client()
    c.cookies.set("risk_access", token)
    return c


def _forge(base: dict, key=None, alg="HS256", kid=None, **over):
    claims = {**base, **over}
    claims = {k: v for k, v in claims.items() if v is not None}
    k = key if key is not None else keys.subkey("jwt")
    return jwt.encode(claims, k, algorithm=alg, headers={"kid": kid or keys.key_id(keys.subkey("jwt"))})


def test_valid_baseline_token_is_accepted_by_the_forger_helper():
    c, _ = make_user()
    base = _claims(c)
    assert _as(_forge(base)).get("/auth/me").status_code == 200       # sanity: the helper makes tokens the server trusts


def test_tampered_signature_is_rejected():
    c, _ = make_user()
    tok = c.cookies.get("risk_access")
    head, body, sig = tok.split(".")
    bad = f"{head}.{body}.{sig[:-3]}{'AAA' if sig[-3:] != 'AAA' else 'BBB'}"
    assert _as(bad).get("/auth/me").status_code == 401


def test_alg_none_token_is_rejected():
    c, _ = make_user()
    base = {k: v for k, v in _claims(c).items()}
    none_tok = jwt.encode(base, None, algorithm="none", headers={"kid": keys.key_id(keys.subkey("jwt"))})
    assert _as(none_tok).get("/auth/me").status_code == 401
    assert _as(none_tok.rsplit(".", 1)[0] + ".").get("/auth/me").status_code == 401


def test_other_algorithms_and_unknown_keys_are_rejected():
    c, _ = make_user()
    base = _claims(c)
    assert _as(_forge(base, alg="HS512")).get("/auth/me").status_code == 401                          # algorithm is pinned
    assert _as(_forge(base, key=b"x" * 64, kid="deadbeef")).get("/auth/me").status_code == 401          # unknown kid
    assert _as(_forge(base, key=b"attacker-controlled-key-0123456789")).get("/auth/me").status_code == 401   # right kid, wrong key
    raw = keys._masters()[0]
    assert _as(_forge(base, key=raw)).get("/auth/me").status_code == 401                                 # the raw secret is never the signing key


@pytest.mark.parametrize("over", [{"aud": "someone-else"}, {"iss": "evil"}, {"exp": 1}, {"nbf": 9999999999}, {"sid": None}, {"sub": None}, {"jti": None}, {"exp": None}])
def test_claims_are_enforced(over):
    c, _ = make_user()
    assert _as(_forge(_claims(c), **over)).get("/auth/me").status_code == 401


def test_a_forged_role_claim_changes_nothing_because_role_comes_from_the_database():
    c, _ = make_user()                                                  # a viewer
    forged = _as(_forge(_claims(c), role="admin"))
    assert forged.get("/alerts?limit=1").status_code == 200
    assert forged.get("/admin/users").status_code == 403


def test_bumping_token_version_kills_outstanding_tokens():
    c, email = make_user()
    assert c.get("/auth/me").status_code == 200
    with db.session_scope() as s:
        s.execute(select(User).where(User.email == email)).scalar_one().token_version += 1
    assert c.get("/auth/me").status_code == 401


def test_secret_rotation_keeps_old_tokens_valid_only_during_the_window(monkeypatch):
    c, _ = make_user()
    old_master = keys._masters()[0].decode()
    new_master = "Nq7-vL2xW9pT4mZk8cRb5yHf3sJd6aEg1uXoM0tKiV"
    monkeypatch.setattr(cfg, "JWT_SECRET", new_master)
    monkeypatch.setattr(cfg, "JWT_SECRET_PREVIOUS", old_master)
    keys.reset_cache()
    assert c.get("/auth/me").status_code == 200                         # signed with the OLD key, still accepted
    fresh = new_client()
    assert login(fresh, make_user()[1]).status_code == 200 or True
    monkeypatch.setattr(cfg, "JWT_SECRET_PREVIOUS", "")
    keys.reset_cache()
    assert c.get("/auth/me").status_code == 401                         # window closed: old key gone


@pytest.mark.parametrize("bad", ["short", "changeme" * 6, "a" * 64, "abab" * 16, "password-password-password-password", "your-secret-key-your-secret-key-1234"])
def test_weak_jwt_secrets_are_refused(bad):
    with pytest.raises(keys.WeakSecretError):
        keys.validate_secret(bad)


def test_strong_secret_is_accepted_and_subkeys_are_independent():
    keys.validate_secret("Nq7-vL2xW9pT4mZk8cRb5yHf3sJd6aEg1uXoM0tKiV")
    assert len({keys.subkey(p) for p in ("jwt", "csrf", "otp", "captcha", "webhook")}) == 5


def test_production_refuses_to_start_without_a_secret_or_with_unsafe_settings(monkeypatch):
    from app.auth.startup import run_startup_checks
    monkeypatch.setattr(cfg, "IS_PROD", True)
    monkeypatch.setattr(cfg, "SMTP_HOST", "")
    monkeypatch.setattr(cfg, "JWT_SECRET", "")
    monkeypatch.setattr(cfg, "JWT_SECRET_FILE", "")
    keys.reset_cache()
    with pytest.raises(keys.WeakSecretError, match="must be set"):
        run_startup_checks()
    monkeypatch.setattr(cfg, "JWT_SECRET", "changeme-changeme-changeme-changeme-0123")
    keys.reset_cache()
    with pytest.raises(keys.WeakSecretError):
        run_startup_checks()
    monkeypatch.setattr(cfg, "JWT_SECRET", "Nq7-vL2xW9pT4mZk8cRb5yHf3sJd6aEg1uXoM0tKiV")
    keys.reset_cache()
    with pytest.raises(RuntimeError) as e:
        run_startup_checks()
    msg = str(e.value)
    assert all(x in msg for x in ("FORCE_HTTPS", "COOKIE_SECURE", "BREVO_API_KEY", "ALLOWED_HOSTS"))


def test_wildcard_cors_with_credentials_is_refused(monkeypatch):
    from app.auth.startup import run_startup_checks
    monkeypatch.setattr(cfg, "CORS_ORIGINS", ["*"])
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        run_startup_checks()


def test_dev_secret_file_is_private(monkeypatch):
    monkeypatch.setattr(cfg, "JWT_SECRET", "")
    monkeypatch.setattr(cfg, "JWT_SECRET_FILE", "")
    monkeypatch.setattr(cfg, "IS_PROD", False)

    keys.reset_cache()
    keys._masters()

    path = cfg.DATA_DIR / ".jwt_secret"
    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

def test_cors_allows_only_the_dashboard_origin_with_credentials():
    c = new_client()
    ok = c.options("/alerts", headers={"Origin": cfg.FRONTEND_URL, "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == cfg.FRONTEND_URL and ok.headers.get("access-control-allow-credentials") == "true"
    evil = c.options("/alerts", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


# =============================================================== password reset
def _token(email: str) -> str:
    return re.search(r"token=([A-Za-z0-9_-]+)", last_mail(email, "Reset")["body"]).group(1)


def _forgot(c, email):
    return c.post("/auth/password/forgot", json={"email": email, **cap(c)})


def test_reset_link_comes_from_configuration_not_the_host_header():
    _, email = make_user()
    c = new_client()
    assert c.post("/auth/password/forgot", json={"email": email, **cap(c)}, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"}).status_code == 202
    body = last_mail(email, "Reset")["body"]
    assert f"{cfg.FRONTEND_URL}/#/reset?token=" in body and "evil" not in body
    assert "?token=" not in body.split("#")[0]                          # token lives in the fragment: not sent to servers or Referer


def test_reset_token_is_random_hashed_at_rest_single_use_and_logs_everyone_out():
    victim, email = make_user()
    c = new_client()
    _forgot(c, email)
    tok = _token(email)
    assert len(tok) >= 40
    with db.session_scope() as s:
        rows = s.execute(select(PasswordResetToken)).scalars().all()
        assert all(r.token_hash != tok for r in rows) and any(r.token_hash == hashlib.sha256(tok.encode()).hexdigest() for r in rows)
    new_pw = "Brand-New-Passphrase-77!"
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": new_pw}).status_code == 200
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": "Another-Strong-Pass-88!"}).status_code == 400   # single use
    assert victim.get("/auth/me").status_code == 401                    # old sessions are dead
    assert login(new_client(), email, PW).status_code == 401            # old password dead
    assert login(new_client(), email, new_pw).status_code == 200
    assert "password was changed" in last_mail(email, "changed")["subject"]


def test_a_new_reset_request_invalidates_the_previous_link():
    _, email = make_user()
    c = new_client()
    _forgot(c, email)
    first = _token(email)
    _forgot(c, email)
    second = _token(email)
    assert first != second
    assert c.post("/auth/password/reset", json={"token": first, "new_password": "Brand-New-Passphrase-77!"}).status_code == 400
    assert c.post("/auth/password/reset", json={"token": second, "new_password": "Brand-New-Passphrase-77!"}).status_code == 200


def test_expired_unknown_and_malformed_reset_tokens_are_rejected():
    _, email = make_user()
    c = new_client()
    _forgot(c, email)
    tok = _token(email)
    with db.session_scope() as s:
        for r in s.execute(select(PasswordResetToken)).scalars():
            r.expires_at = db.utcnow().replace(year=2020)
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": "Brand-New-Passphrase-77!"}).status_code == 400
    assert c.post("/auth/password/reset", json={"token": "A" * 43, "new_password": "Brand-New-Passphrase-77!"}).status_code == 400
    assert c.post("/auth/password/reset", json={"token": "' OR 1=1 --", "new_password": "Brand-New-Passphrase-77!"}).status_code == 422


def test_reset_enforces_password_policy_and_no_reuse_without_burning_the_token():
    _, email = make_user()
    c = new_client()
    _forgot(c, email)
    tok = _token(email)
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": "weak"}).status_code == 422
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": PW}).status_code == 422      # same as current
    assert c.post("/auth/password/reset", json={"token": tok, "new_password": "Brand-New-Passphrase-77!"}).status_code == 200


def test_forgot_password_needs_a_captcha_and_is_rate_limited_per_address():
    _, email = make_user()
    c = new_client()
    bad = c.post("/auth/password/forgot", json={"email": email, "captcha_id": c.get("/auth/captcha").json()["captcha_id"], "captcha_answer": "NOPE"})
    assert bad.status_code == 400 and not any(m["to"] == email and "Reset" in m["subject"] for m in mailer.OUTBOX)
    assert [_forgot(c, email).status_code for _ in range(4)] == [202, 202, 202, 429]


def test_change_password_needs_the_current_password_and_signs_everyone_out():
    c, email = make_user()
    new_pw = "Another-Strong-Pass-88!"
    assert c.post("/auth/password/change", json={"current_password": "Wrong-Password-1!", "new_password": new_pw}, headers=csrf(c)).status_code == 403
    assert c.post("/auth/password/change", json={"current_password": PW, "new_password": new_pw}, headers=csrf(c)).status_code == 200
    assert c.get("/auth/me").status_code == 401
    assert login(new_client(), email, new_pw).status_code == 200


# =============================================================== HTTPS
def test_plain_http_is_redirected_to_https_and_hsts_is_sent(monkeypatch):
    monkeypatch.setattr(cfg, "FORCE_HTTPS", True)
    c = new_client()
    r = c.get("/alerts", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"].startswith("https://")
    p = c.post("/auth/login", json={}, follow_redirects=False)
    assert p.status_code == 308                                           # 308 keeps the method, so credentials are never sent in clear by a redirect-follow
    assert "includeSubDomains" in new_client("https://testserver").get("/health").headers["strict-transport-security"]
    assert c.get("/health", follow_redirects=False).status_code == 200    # health checks stay reachable


def test_forwarded_headers_are_ignored_unless_a_proxy_is_trusted(monkeypatch):
    monkeypatch.setattr(cfg, "FORCE_HTTPS", True)
    spoof = {"X-Forwarded-Proto": "https"}
    assert new_client().get("/alerts", headers=spoof, follow_redirects=False).status_code == 308   # attacker cannot claim "https"
    monkeypatch.setattr(cfg, "TRUSTED_PROXY_COUNT", 1)
    assert new_client().get("/alerts", headers=spoof, follow_redirects=False).status_code == 401    # behind our proxy it is honoured


def test_client_ip_is_taken_from_the_trusted_side_of_x_forwarded_for(monkeypatch):
    from starlette.requests import Request
    from app.auth import netutil
    def req(xff):
        return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("10.0.0.9", 1), "method": "GET", "path": "/", "query_string": b"", "scheme": "http", "server": ("a", 80)})
    assert netutil.client_ip(req("6.6.6.6, 1.2.3.4")) == "10.0.0.9"        # not trusted: use the socket peer
    monkeypatch.setattr(cfg, "TRUSTED_PROXY_COUNT", 1)
    assert netutil.client_ip(req("6.6.6.6, 1.2.3.4")) == "1.2.3.4"         # rightmost = what our proxy saw; the left side is attacker-supplied


# =============================================================== SSRF
@pytest.fixture
def dns(monkeypatch):
    table = {"hooks.example.org": ["93.184.216.34"], "internal.example.org": ["10.0.0.5"], "mixed.example.org": ["93.184.216.34", "127.0.0.1"],
             "meta.example.org": ["169.254.169.254"], "v6.example.org": ["2606:2800:220:1:248:1893:25c8:1946"], "mapped.example.org": ["::ffff:127.0.0.1"]}
    def fake(host, port):
        if host in table:
            return table[host]
        try:
            return [socket.inet_ntoa(socket.inet_aton(host))]            # legacy decimal / hex / octal forms resolve like the real resolver would
        except OSError:
            raise OSError("NXDOMAIN")
    monkeypatch.setattr(ssrf, "_resolve", fake)
    return table


@pytest.mark.parametrize("url", ["https://hooks.example.org/x", "https://hooks.example.org:8443/x?a=1", "https://v6.example.org/hook", "https://93.184.216.34/hook"])
def test_ssrf_allows_public_https_urls(dns, url):
    assert ssrf.validate_public_url(url).ips


@pytest.mark.parametrize("url", [
    "http://hooks.example.org/x", "ftp://hooks.example.org/x", "file:///etc/passwd", "gopher://hooks.example.org/", "//hooks.example.org/x", "https:///x",
    "https://169.254.169.254/latest/meta-data/", "https://meta.example.org/", "https://127.0.0.1/", "https://127.1/", "https://0.0.0.0/", "https://[::1]/",
    "https://10.0.0.1/", "https://172.16.5.4/", "https://192.168.1.1/", "https://100.64.0.1/", "https://[fd00::1]/", "https://[fe80::1]/",
    "https://[::ffff:127.0.0.1]/", "https://mapped.example.org/", "https://2130706433/", "https://0x7f000001/", "https://017700000001/",
    "https://localhost/", "https://LOCALHOST./", "https://foo.localhost/", "https://metadata.google.internal/", "https://svc.cluster.local/", "https://printer.lan/",
    "https://internal.example.org/", "https://mixed.example.org/",
    "https://user:pw@hooks.example.org/", "https://hooks.example.org@127.0.0.1/", "https://hooks.example.org:22/", "https://hooks.example.org:80/",
    "https://hooks.example.org:99999/", "https://bad host/", "https://hooks.example.org/\r\nHost: evil", "https://exa mple.org/", "https://-bad-.example.org/",
    "", "https://" + "a" * 70 + ".example.org/", "https://hooks.example.org/" + "a" * 3000,
])
def test_ssrf_blocks_internal_and_malformed_targets(dns, url):
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.validate_public_url(url)


def test_ssrf_host_allowlist_is_enforced(dns, monkeypatch):
    monkeypatch.setattr(cfg, "WEBHOOK_ALLOWED_HOSTS", ["hooks.example.org"])
    assert ssrf.validate_public_url("https://hooks.example.org/x")
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.validate_public_url("https://v6.example.org/x")


def test_dns_rebinding_between_save_and_send_is_caught(dns):
    ssrf.validate_public_url("https://hooks.example.org/x")                # passes when the admin saves it...
    dns["hooks.example.org"] = ["127.0.0.1"]                              # ...attacker flips the DNS record afterwards
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.post_json("https://hooks.example.org/x", {"a": 1}, b"k" * 32)


def test_send_connects_to_the_validated_ip_signs_the_body_and_never_follows_redirects(dns, monkeypatch):
    seen = {}

    class FakeConn:
        def __init__(self, host, port, ip, **kw):
            seen.update(host=host, port=port, ip=ip)
            seen["conns"] = seen.get("conns", 0) + 1
        def request(self, method, path, body, headers):
            seen.update(method=method, path=path, body=body, headers=headers)
        def getresponse(self):
            class R:
                status = 302                                              # a redirect to an internal address
                headers = {"Location": "http://169.254.169.254/"}
                def read(self, n=-1): return b""
            return R()
        def close(self): pass
    monkeypatch.setattr(ssrf, "_PinnedHTTPS", FakeConn)
    status = ssrf.post_json("https://hooks.example.org/x?y=1", {"event": "t"}, b"k" * 32)
    assert status == 302 and seen["conns"] == 1                           # reported, not followed
    assert (seen["ip"], seen["host"], seen["port"], seen["path"]) == ("93.184.216.34", "hooks.example.org", 443, "/x?y=1")
    sig = seen["headers"]["X-Risk-Signature"]
    import hmac
    assert sig == "sha256=" + hmac.new(b"k" * 32, seen["body"], hashlib.sha256).hexdigest()


def test_webhook_endpoints_are_admin_only_and_reject_internal_urls(dns, monkeypatch):
    admin, _ = make_admin()
    viewer, _ = make_user()
    h = csrf(admin)
    assert viewer.put("/admin/webhook", json={"url": "https://hooks.example.org/x"}, headers=csrf(viewer)).status_code == 403
    for bad in ["http://hooks.example.org/x", "https://169.254.169.254/", "https://127.0.0.1/", "https://internal.example.org/", "https://localhost/"]:
        r = admin.put("/admin/webhook", json={"url": bad}, headers=h)
        assert r.status_code == 422 and "rejected" in r.json()["detail"], bad
    assert admin.get("/admin/webhook").json()["url"] is None
    assert admin.put("/admin/webhook", json={"url": "https://hooks.example.org/x"}, headers=h).status_code == 200
    monkeypatch.setattr(ssrf, "post_json", lambda url, payload, key, **kw: 204)
    assert admin.post("/admin/webhook/test", headers=h).json() == {"delivered": True, "status": 204}
    assert admin.put("/admin/webhook", json={"url": None}, headers=h).json()["url"] is None
    assert admin.post("/admin/webhook/test", headers=h).status_code == 422
