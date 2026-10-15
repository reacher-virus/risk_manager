
"""Security-relevant plumbing: Brevo email, header injection, admin CLI, bootstrap, and webhook sender."""

import json
import logging
import time
import types
from contextlib import contextmanager
from urllib.error import URLError

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
    yield
    mailer.OUTBOX.clear()


def test_brevo_sends_email_with_api_key_and_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(cfg, "BREVO_API_KEY", "test-api-key", raising=False)
    monkeypatch.setattr(
        cfg, "MAIL_FROM", "Risk Manager <verified@example.org>"
    )
    monkeypatch.setattr(mailer, "urlopen", fake_urlopen)

    mailer.send_email("ana@example.org", "Hello", "Body 123456")

    assert captured["url"] == mailer.BREVO_URL
    assert captured["headers"]["Api-key"] == "test-api-key"
    assert captured["timeout"] == 15
    assert captured["payload"]["sender"]["email"] == "verified@example.org"
    assert captured["payload"]["to"] == [{"email": "ana@example.org"}]
    assert captured["payload"]["subject"] == "Hello"
    assert captured["payload"]["textContent"] == "Body 123456"
    assert not mailer.OUTBOX


def test_brevo_failure_never_raises_or_logs_the_code(
    monkeypatch, caplog
):
    def failing_urlopen(request, timeout):
        raise URLError("service unavailable")

    monkeypatch.setattr(cfg, "BREVO_API_KEY", "test-api-key", raising=False)
    monkeypatch.setattr(
        cfg, "MAIL_FROM", "Risk Manager <verified@example.org>"
    )
    monkeypatch.setattr(mailer, "urlopen", failing_urlopen)

    with caplog.at_level(logging.DEBUG):
        mailer.send_email(
            "ana@example.org", "Your code", "Your code is 987654"
        )

    assert "987654" not in caplog.text
    assert "ana@example.org" not in caplog.text


def test_production_without_brevo_key_sends_nothing(
    monkeypatch, caplog
):
    monkeypatch.setattr(cfg, "IS_PROD", True)
    monkeypatch.setattr(cfg, "BREVO_API_KEY", "", raising=False)

    def unexpected_request(*args, **kwargs):
        pytest.fail("Brevo must not be called without an API key")

    monkeypatch.setattr(mailer, "urlopen", unexpected_request)

    with caplog.at_level(logging.DEBUG):
        mailer.send_email(
            "ana@example.org", "Your code", "Your code is 987654"
        )

    assert not mailer.OUTBOX
    assert "987654" not in caplog.text
    assert "ana@example.org" not in caplog.text


@pytest.mark.parametrize(
    "subject",
    [
        "Hi\r\nBcc: evil@example.net",
        "Hi\nBcc: evil@example.net",
    ],
)
def test_header_injection_through_a_subject_is_impossible(subject):
    with pytest.raises(ValueError):
        mailer.send_email("ana@example.org", subject, "x")


def test_admin_cli_creates_a_verified_active_admin(monkeypatch, capsys):
    from app.auth import create_admin

    email = uniq("cli")
    answers = {
        "Admin email: ": email,
        "Full name [Administrator]: ": "Root User",
    }
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": answers[prompt]
    )
    monkeypatch.setattr(
        create_admin.getpass, "getpass", lambda prompt="": ADMIN_PW
    )

    assert create_admin.main() == 0

    with db.session_scope() as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one()

        assert (
            user.role,
            user.status,
            user.email_verified,
            user.full_name,
        ) == ("admin", "active", True, "Root User")
        assert user.password_hash.startswith("$argon2id$")


def test_admin_cli_rejects_mismatched_weak_and_duplicate_passwords(
    monkeypatch, capsys
):
    from app.auth import create_admin

    email = uniq("cli")
    answers = iter(
        ["Vault-Keeper-9-Lantern!", "something-else-entirely"]
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": email if "email" in prompt else "",
    )
    monkeypatch.setattr(
        create_admin.getpass, "getpass", lambda prompt="": next(answers)
    )

    assert create_admin.main() == 1
    assert "do not match" in capsys.readouterr().err

    monkeypatch.setattr(
        create_admin.getpass, "getpass", lambda prompt="": "weak"
    )
    assert create_admin.main() == 1
    assert "Password" in capsys.readouterr().err

    monkeypatch.setattr(
        create_admin.getpass, "getpass", lambda prompt="": ADMIN_PW
    )
    assert create_admin.main() == 0

    assert create_admin.main() == 1
    assert "already exists" in capsys.readouterr().err


def test_create_admin_validates_everything():
    with db.session_scope() as session:
        invalid_inputs = (
            {"email_raw": "x@mailinator.com", "password": ADMIN_PW},
            {"email_raw": uniq(), "password": "weak"},
            {
                "email_raw": uniq(),
                "password": ADMIN_PW,
                "full_name": "<script>",
            },
        )

        for kwargs in invalid_inputs:
            with pytest.raises(Exception):
                service.create_admin(session, **kwargs)


def _fake_scope(admin_count: int, created: list):
    class FakeSession:
        def execute(self, *args, **kwargs):
            return types.SimpleNamespace(
                scalar_one=lambda: admin_count
            )

    @contextmanager
    def scope():
        yield FakeSession()

    return scope


def test_bootstrap_creates_the_first_admin_only_when_none_exists(
    monkeypatch, caplog
):
    created = []

    monkeypatch.setattr(cfg, "AUTH_REQUIRED", True)
    monkeypatch.setattr(
        service,
        "create_admin",
        lambda session, email, password, *args: created.append(
            (email, password)
        ),
    )
    monkeypatch.setattr(cfg, "ADMIN_EMAIL", "boss@example.org")
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", ADMIN_PW)
    monkeypatch.setattr(db, "session_scope", _fake_scope(1, created))

    startup.bootstrap_admin()
    assert created == []

    monkeypatch.setattr(db, "session_scope", _fake_scope(0, created))

    with caplog.at_level(logging.WARNING):
        startup.bootstrap_admin()

    assert created == [("boss@example.org", ADMIN_PW)]
    assert "Remove ADMIN_PASSWORD" in caplog.text

    created.clear()
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", "")

    with caplog.at_level(logging.WARNING):
        startup.bootstrap_admin()

    assert created == []
    assert "create_admin" in caplog.text

    monkeypatch.setattr(cfg, "AUTH_REQUIRED", False)
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD", ADMIN_PW)
    startup.bootstrap_admin()
    assert created == []


def test_critical_alert_webhook_sends_a_signed_event_through_the_ssrf_guard(
    monkeypatch,
):
    sent = []

    monkeypatch.setattr(
        db,
        "get_setting",
        lambda key, default=None: (
            "https://hooks.example.org/x"
            if key == "webhook_url"
            else default
        ),
    )
    monkeypatch.setattr(
        ssrf,
        "post_json",
        lambda url, payload, key, **kwargs: (
            sent.append((url, payload, key)) or 200
        ),
    )

    webhook.notify_critical(
        "TX-1", "C-1", 5200.0, 0.97, "HOLD_FOR_VERIFICATION"
    )

    for _ in range(50):
        if sent:
            break
        time.sleep(0.05)

    assert sent, "Expected the webhook to be sent"

    url, payload, key = sent[0]
    assert url == "https://hooks.example.org/x"
    assert len(key) == 32
    assert payload["event"] == "critical_alert"
    assert payload["transaction_id"] == "TX-1"
    assert payload["risk_score"] == 0.97


def test_webhook_failures_and_blocked_targets_are_audited_not_raised(
    monkeypatch,
):
    def blocked(*args, **kwargs):
        raise ssrf.UnsafeURL(
            "Host resolves to a non-public address"
        )

    monkeypatch.setattr(ssrf, "post_json", blocked)
    webhook._send(
        "https://hooks.example.org/x", {"event": "test"}
    )

    monkeypatch.setattr(
        ssrf,
        "post_json",
        lambda *args, **kwargs: (
            _ for _ in ()
        ).throw(TimeoutError()),
    )
    webhook._send(
        "https://hooks.example.org/x", {"event": "test"}
    )

    from app.core.db import AuditLog

    with db.session_scope() as session:
        actions = [
            row.action
            for row in session.execute(
                select(AuditLog)
                .order_by(AuditLog.id.desc())
                .limit(4)
            ).scalars()
        ]

    assert "WEBHOOK_BLOCKED" in actions
    assert "WEBHOOK_FAILED" in actions


def test_no_webhook_configured_means_no_thread_and_no_request(
    monkeypatch,
):
    monkeypatch.setattr(db, "get_setting", lambda key, default=None: None)
    monkeypatch.setattr(
        ssrf,
        "post_json",
        lambda *args, **kwargs: pytest.fail("must not send"),
    )

    webhook.notify_critical(
        "TX-2", "C-2", 1.0, 0.9, "REVIEW"
    )
