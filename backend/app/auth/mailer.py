"""Outbound email (plain text only: no HTML, so no markup injection). SMTP in production; console/outbox in development."""
import logging
import smtplib
import ssl
from collections import deque
from email.message import EmailMessage

from app.core import config as cfg

log = logging.getLogger("risk.mail")
OUTBOX: deque = deque(maxlen=200)       # development / test inspection only


def smtp_configured() -> bool:
    return bool(cfg.SMTP_HOST)


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.MAIL_FROM, to, subject     # EmailMessage rejects CR/LF in headers
    msg.set_content(body)
    if not smtp_configured():
        if cfg.IS_PROD:
            log.error("SMTP is not configured; refusing to send mail in production")
            return
        OUTBOX.append({"to": to, "subject": subject, "body": body})
        log.warning("[DEV MAIL] to=%s subject=%s\n%s", to, subject, body)   # never reached in production
        return
    try:
        ctx = ssl.create_default_context()
        if cfg.SMTP_SSL:
            server = smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT, context=ctx, timeout=10)
        else:
            server = smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=10)
            server.starttls(context=ctx)
        with server:
            if cfg.SMTP_USER:
                server.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception:
        log.exception("Failed to send email to a user (details omitted)")   # the body (which holds the code) is never logged
