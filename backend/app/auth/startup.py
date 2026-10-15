"""Fail-fast startup validation + first-admin bootstrap."""
import logging

from sqlalchemy import func, select

from app.auth import mailer, service
from app.auth import secrets as keys
from app.auth.models import User
from app.core import config as cfg
from app.core import db

log = logging.getLogger("risk.auth")


def run_startup_checks() -> None:
    keys.reset_cache()
    keys._masters()                                                     # raises WeakSecretError for a weak/missing secret
    if "*" in cfg.CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS must list explicit origins: '*' cannot be combined with cookie credentials")
    if cfg.IS_PROD:
        problems = []
        if not cfg.FORCE_HTTPS:
            problems.append("FORCE_HTTPS must be true")
        if not cfg.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true")
        if not mailer.smtp_configured():
            problems.append("BREVO_API_KEY must be configured (one-time codes are sent by email)")
        if not cfg.FRONTEND_URL.startswith("https://") or any(not o.startswith("https://") for o in cfg.CORS_ORIGINS):
            problems.append("FRONTEND_URL and CORS_ORIGINS must be https:// URLs")
        if not cfg.ALLOWED_HOSTS or "*" in cfg.ALLOWED_HOSTS:
            problems.append("ALLOWED_HOSTS must list your domain(s)")
        if not cfg.AUTH_REQUIRED:
            problems.append("RISK_AUTH_REQUIRED cannot be false")
        if problems:
            raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    bootstrap_admin()


def bootstrap_admin() -> None:
    if not cfg.AUTH_REQUIRED:
        return
    with db.session_scope() as s:
        if s.execute(select(func.count()).select_from(User).where(User.role == "admin")).scalar_one():
            return
        if cfg.ADMIN_EMAIL and cfg.ADMIN_PASSWORD:
            service.create_admin(s, cfg.ADMIN_EMAIL, cfg.ADMIN_PASSWORD)
            log.warning("Created the first admin account from ADMIN_EMAIL/ADMIN_PASSWORD. Remove ADMIN_PASSWORD from the environment now.")
        else:
            log.warning("No admin account exists. Create one:  python -m app.auth.create_admin")
