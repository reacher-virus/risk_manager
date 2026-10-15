"""Test fixtures. The whole pipeline (data -> features -> train) runs ONCE on a small dataset in a temp dir."""
import os
import tempfile

# must be set before any `app.*` import so config picks it up
_TMP = tempfile.mkdtemp(prefix="risk-test-")
os.environ["RISK_DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/risk-test.db"
os.environ.pop("API_KEYS", None)
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["RISK_AUTH_REQUIRED"] = "false"      # the pre-auth API tests run in open dev mode; auth tests turn it back on
os.environ["RISK_ARGON2_FAST"] = "1"  # Use cheaper hashing so the test suite stays fast.
os.environ["TRUSTED_PROXY_COUNT"] = "0"  # Tests use direct requests, not a trusted proxy.

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def pipeline():
    import pandas as pd
    from app.core.config import PROCESSED_PATH, RAW_PATH
    from app.data.generate_dataset import generate_dataset
    from app.ml import train
    from app.ml.features import engineer_features

    raw = generate_dataset(n_customers=1500, seed=7)
    raw.to_csv(RAW_PATH, index=False)
    engineer_features(raw).to_csv(PROCESSED_PATH, index=False)
    manifest = train.main()
    return {"raw": raw, "manifest": manifest}


@pytest.fixture(scope="session")
def client(pipeline):
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    from app.core import security
    security.reset_rate_limits()
    yield

@pytest.fixture(autouse=True)
def _capture_test_emails(monkeypatch, request):
    from app.auth import mailer

    mailer.OUTBOX.clear()

    smtp_tests = {
        "test_smtp_uses_starttls_with_certificate_verification_and_credentials",
        "test_implicit_tls_option",
        "test_smtp_failure_never_raises_and_never_logs_the_code",
    }

    if request.node.name not in smtp_tests:
        monkeypatch.setattr(mailer, "smtp_configured", lambda: False)

    yield
    mailer.OUTBOX.clear()

@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    from app.core.db import init_db
    init_db()