
"""Outbound email via Brevo HTTPS API; console/outbox in development."""
import json
import logging
from collections import deque
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core import config as cfg

log = logging.getLogger("risk.mail")
OUTBOX: deque = deque(maxlen=200)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
def smtp_configured() -> bool:
    return bool(getattr(cfg, "BREVO_API_KEY", ""))


def send_email(to: str, subject: str, body: str) -> None:
    api_key = getattr(cfg, "BREVO_API_KEY", "")

    if not api_key:
        if cfg.IS_PROD:
            log.error("Brevo API key is not configured; refusing to send mail")
            return

        OUTBOX.append({"to": to, "subject": subject, "body": body})
        log.warning("[DEV MAIL] to=%s subject=%s\n%s", to, subject, body)
        return

    sender_name, sender_email = parseaddr(cfg.MAIL_FROM)
    if not sender_email:
        log.error("Mail sender address is invalid")
        return

    payload = {
        "sender": {
            "name": sender_name or "Risk Manager",
            "email": sender_email,
        },
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }

    request = Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            if response.status not in (200, 201, 202):
                log.error(
                    "Brevo returned unexpected status: %s",
                    response.status,
                )
    except HTTPError as exc:
        log.error("Brevo rejected email request; HTTP status=%s", exc.code)
    except (URLError, TimeoutError, OSError):
        log.exception("Brevo email request failed; recipient details omitted")
