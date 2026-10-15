"""Critical-alert webhook. The URL is admin-configured, so every send goes through the SSRF guard."""
import threading
from datetime import datetime, timezone

from app.auth import secrets as keys
from app.core import db, ssrf


def _send(url: str, payload: dict) -> None:
    try:
        ssrf.post_json(url, payload, keys.subkey("webhook"))
    except ssrf.UnsafeURL:
        db.audit("system", "WEBHOOK_BLOCKED", detail={"reason": "URL failed the SSRF check at send time"})
    except Exception as e:                                              # network failures must never break scoring
        db.audit("system", "WEBHOOK_FAILED", detail={"error": type(e).__name__})


def notify_critical(tx_id: str, customer_id: str, amount: float, risk_score: float, decision: str) -> None:
    url = db.get_setting("webhook_url")
    if not url:
        return
    payload = {"event": "critical_alert", "transaction_id": tx_id, "customer_id": customer_id, "amount": amount,
               "risk_score": risk_score, "decision": decision, "at": datetime.now(timezone.utc).isoformat()}
    threading.Thread(target=_send, args=(url, payload), daemon=True).start()
