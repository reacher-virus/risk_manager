"""Security-relevant plumbing: SMTP over verified TLS, mail header injection, the admin CLI, first-admin bootstrap, webhook sender."""
import logging
import ssl
import time
import types
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.auth import mailer, service, startup
from app.auth.models import User
from app.core import config as cfg
from app.core import db, ssrf, webhook
from tests.auth_helpers import ADMIN_PW, uniq


@pytest.fixture(autouse=True)
def clean_outbox():
    mailer.OUTBOX.clear()


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls, self.sent = [], []
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.calls.append(("starttls", context))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.sent.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_smtp_uses_starttls_with_certificate_verification_and_credentials(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(cfg, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(cfg, "SMTP_USER", "mailer")
    monkeypatch.setattr(cfg, "SMTP_PASSWORD", "s3cret")
    monkeypatch.setattr(cfg, "SMTP_SSL", False)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.send_email("ana@example.org", "Hello", "Body 123456")
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("smtp.example.org", cfg.SMTP_PORT) and s.timeout == 10
    kind, ctx = s.calls[0]
    assert kind == "starttls" and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True     # no silent downgrade to unverified TLS
    assert s.calls[1] == ("login", "mailer", "s3cret")
    assert s.sent[0]["To"] == "ana@example.org" and s.sent[0]["Subject"] == "Hello"
    assert not mailer.OUTBOX                                                                               # real SMTP never touches the dev outbox


def test_implicit_tls_option(monkeypatch):
    seen = {}
    class SSLFake(FakeSMTP):
        def __init__(self, host, port, timeout=None, context=None):
            super().__init__(host, port, timeout, context)
            seen["ctx"] = context
    monkeypatch.setattr(cfg, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(cfg, "SMTP_SSL", True)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", SSLFake)
    mailer.send_email("ana@example.org", "Hi", "x")
    assert seen["ctx"].verify_mode == ssl.CERT_REQUIRED


def test_smtp_failure_never_raises_and_never_logs_the_code(monkeypatch, caplog):
    class Boom(FakeSMTP):
        def send_message(self, msg):
            raise ConnectionError("smtp down")
    monkeypatch.setattr(cfg, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(mailer.smtplib, "SMTP", Boom)
    with caplog.at_level(logging.DEBUG):
        mailer.send_email("ana@example.org", "Your code", "Your code is 987654")
    assert "987654" not in caplog.text and "ana@example.org" not in caplog.text


def test_production_without_smtp_sends_nothing_and_stores_nothing(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "IS_PROD", True)
    monkeypatch.setattr(cfg, "SMTP_HOST", "")
    with caplog.at_level(logging.DEBUG):
        mailer.send_email("ana@example.org", "Your code", "Your code is 987654")
    assert not mailer.OUTBOX and "987654" not in caplog.text                                              # the dev console/outbox path is dev-only


@pytest.mark.parametrize("subject", ["Hi\r\nBcc: evil@example.net", "Hi\nBcc: evil@example.net"])
def test_header_injection_through_a_subject_is_impossible(subject):
    with pytest.raises(ValueError):
        mailer.send_email("ana@example.org", subject, "x")


def test_admin_cli_creates_a_verified_active_admin(monkeypatch, capsys):
    from app.auth import create_admin
    email = uniq("cli")
    monkeypatch.setattr("builtins.input", lambda prompt="": {"Admin email: ": email, "Full name [Administrator]: ": "Root User"}[prompt])
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": ADMIN_PW)
    assert create_admin.main() == 0
    with db.session_scope() as s:
        u = s.execute(select(User).where(User.email == email)).scalar_one()
        assert (u.role, u.status, u.email_verified, u.full_name) == ("admin", "active", True, "Root User")
        assert u.password_hash.startswith("$argon2id$")


def test_admin_cli_rejects_mismatched_weak_and_duplicate_passwords(monkeypatch, capsys):
    from app.auth import create_admin
    email = uniq("cli")
    answers = iter(["Vault-Keeper-9-Lantern!", "something-else-entirely"])
    monkeypatch.setattr("builtins.input", lambda prompt="": email if "email" in prompt else "")
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": next(answers))
    assert create_admin.main() == 1 and "do not match" in capsys.readouterr().err
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": "weak")
    assert create_admin.main() == 1 and "Password" in capsys.readouterr().err
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": ADMIN_PW)
    assert create_admin.main() == 0
    assert create_admin.main() == 1 and "already exists" in capsys.readouterr().err


def test_create_admin_validates_everything():
    with db.session_scope() as s:
        for kwargs in ({"email_raw": "x@mailinator.com", "password": ADMIN_PW}, {"email_raw": uniq(), "password": "weak"},
                       {"email_raw": uniq(), "password": ADMIN_PW, "full_name": "<script>"}):
            with pytest.raises(Exception):
                service.create_admin(s, **kwargs)


def _fake_scope(admin_count: int, created: list):
    class FakeS:
        def execute(self, *a, **k):
            return types.SimpleNamespace(scalar_one=lambda: admin_count)
    @contextmanager
    def scope():
        yield FakeS()
    return scope


def test_bootstrap_creates_the_first_admin_only_when_none_exists(monkeypatch, caplog):
    created: list = []
    monkeypatch.setattr(cfg, "AUTH_REQUIRED", True)
    monkeypatch.setattr(service, "create_admin", lambda s, e, p, *a: created.append((e, p)))
    monkeypatch.setattr(cfg, "ADMIN_EMAIL", "boss@example.org")
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", ADMIN_PW)
    monkeypatch.setattr(db, "session_scope", _fake_scope(1, created))
    startup.bootstrap_admin()
    assert created == []                                                  # an admin already exists: never overwrite or duplicate
    monkeypatch.setattr(db, "session_scope", _fake_scope(0, created))
    with caplog.at_level(logging.WARNING):
        startup.bootstrap_admin()
    assert created == [("boss@example.org", ADMIN_PW)] and "Remove ADMIN_PASSWORD" in caplog.text
    created.clear()
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", "")
    with caplog.at_level(logging.WARNING):
        startup.bootstrap_admin()
    assert created == [] and "create_admin" in caplog.text
    monkeypatch.setattr(cfg, "AUTH_REQUIRED", False)
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", ADMIN_PW)
    startup.bootstrap_admin()
    assert created == []                                                  # open dev mode needs no admin


def test_critical_alert_webhook_sends_a_signed_event_through_the_ssrf_guard(monkeypatch):
    sent = []
    monkeypatch.setattr(db, "get_setting", lambda k, d=None: "https://hooks.example.org/x" if k == "webhook_url" else d)
    monkeypatch.setattr(ssrf, "post_json", lambda url, payload, key, **kw: sent.append((url, payload, key)) or 200)
    webhook.notify_critical("TX-1", "C-1", 5200.0, 0.97, "HOLD_FOR_VERIFICATION")
    for _ in range(50):
        if sent:
            break
        time.sleep(0.05)
    url, payload, key = sent[0]
    assert url == "https://hooks.example.org/x" and len(key) == 32
    assert payload["event"] == "critical_alert" and payload["transaction_id"] == "TX-1" and payload["risk_score"] == 0.97


def test_webhook_failures_and_blocked_targets_are_audited_not_raised(monkeypatch):
    def boom(*a, **k):
        raise ssrf.UnsafeURL("Host resolves to a non-public address")
    monkeypatch.setattr(ssrf, "post_json", boom)
    webhook._send("https://hooks.example.org/x", {"event": "t"})
    monkeypatch.setattr(ssrf, "post_json", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    webhook._send("https://hooks.example.org/x", {"event": "t"})
    from app.core.db import AuditLog
    with db.session_scope() as s:
        actions = [r.action for r in s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(4)).scalars()]
    assert "WEBHOOK_BLOCKED" in actions and "WEBHOOK_FAILED" in actions


def test_no_webhook_configured_means_no_thread_and_no_request(monkeypatch):
    monkeypatch.setattr(db, "get_setting", lambda k, d=None: None)
    monkeypatch.setattr(ssrf, "post_json", lambda *a, **k: pytest.fail("must not send"))
    webhook.notify_critical("TX-2", "C-2", 1.0, 0.9, "REVIEW")
