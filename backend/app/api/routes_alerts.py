"""Alert queue, alert detail, analyst review workflow, CSV export."""
import csv
import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.rings import get_rings, ring_of_customer
from app.api.state import S, build_alerts, status_of, tx_record
from app.core import db
from app.core.risk_policy import min_score_for
from app.core.schemas import ReviewIn
from app.core.security import principal, require_analyst

router = APIRouter()
STATUSES = "ALL|NEW|APPROVED|HELD|ESCALATED"


def _candidates(source, min_level, status, sort) -> pd.DataFrame:
    thr, rv = S.threshold(), db.review_state()
    lo = min_score_for(min_level, thr)
    parts = []
    if source in ("test", "all"):
        d = S.test_df[S.test_df["risk_score"] >= lo][["transaction_id", "risk_score", "timestamp"]].copy()
        d["source"] = "test"
        parts.append(d)
    if source in ("live", "all"):
        live = db.live_dataframe()
        parts.append(live[live["risk_score"] >= lo][["transaction_id", "risk_score", "timestamp", "source"]])
    cand = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["transaction_id", "risk_score", "timestamp", "source"])
    cand["status"] = cand["transaction_id"].map(lambda t: status_of(rv.get(t)))
    if status != "ALL":
        cand = cand[cand["status"] == status]
    return cand.sort_values("risk_score" if sort == "risk" else "timestamp", ascending=False)


def _items(page: pd.DataFrame) -> list[dict]:
    recs = [r for r in (tx_record(t) for t in page["transaction_id"]) if r]
    return build_alerts(recs, db.review_state())


@router.get("/alerts")
def list_alerts(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0), min_level: str = "HIGH",
                status: str = Query("ALL", pattern=f"^({STATUSES})$"), source: str = Query("all", pattern="^(test|live|all)$"),
                sort: str = Query("risk", pattern="^(risk|time)$"), p: dict = Depends(principal)):
    cand = _candidates(source, min_level, status, sort)
    return {"total": int(len(cand)), "threshold": S.threshold(), "items": _items(cand.iloc[offset:offset + limit])}


@router.get("/alerts/export.csv")
def export_alerts(min_level: str = "HIGH", status: str = Query("ALL", pattern=f"^({STATUSES})$"),
                  source: str = Query("all", pattern="^(test|live|all)$"), p: dict = Depends(principal)):
    items = _items(_candidates(source, min_level, status, "risk").head(5000))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["transaction_id", "customer_id", "amount", "risk_score", "risk_level", "decision", "status", "label", "source", "timestamp", "reasons"])
    for a in items:
        w.writerow([a["transaction_id"], a["customer_id"], a["amount"], a["risk_score"], a["risk_level"], a["decision"],
                    a["status"], a["label"] or "", a["source"], a["timestamp"], " | ".join(a["reasons"])])
    db.audit(p["actor"], "EXPORT_ALERTS", detail={"rows": len(items)})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=alerts.csv"})


@router.get("/alerts/{tx_id}")
def alert_detail(tx_id: str, p: dict = Depends(principal)):
    rec = tx_record(tx_id)
    if not rec:
        raise HTTPException(404, "Transaction not found")
    alert = build_alerts([rec], db.review_state())[0]
    comb = S.combined_df()
    mine = comb[comb["customer_id"] == rec["customer_id"]].sort_values("timestamp").tail(15)
    timeline = [{"transaction_id": r.transaction_id, "timestamp": str(r.timestamp), "amount": float(r.amount),
                 "risk_score": round(float(r.risk_score), 4), "device_id": r.device_id, "ip_region": r.ip_region}
                for r in mine.itertuples()]
    shared = comb[((comb["device_id"] == rec["device_id"]) | (comb["payment_id"] == rec["payment_id"]))
                  & (comb["customer_id"] != rec["customer_id"])]
    related = []
    for cust, g in shared.groupby("customer_id"):
        via = [n for n, hit in (("device", (g["device_id"] == rec["device_id"]).any()), ("card", (g["payment_id"] == rec["payment_id"]).any())) if hit]
        related.append({"customer_id": cust, "transactions": int(len(g)), "max_risk": round(float(g["risk_score"].max()), 4), "shared_via": via})
    related.sort(key=lambda r: r["max_risk"], reverse=True)
    return {**alert, "device_id": rec["device_id"], "payment_id": rec["payment_id"], "ip_region": rec["ip_region"],
            "merchant_category": rec["merchant_category"], "payment_method": rec["payment_method"],
            "account_age_days": rec["account_age_days"], "features": rec["features"], "customer_timeline": timeline,
            "related_accounts": related[:25], "ring_id": ring_of_customer(rec["customer_id"]),
            "review_history": db.review_history(tx_id), "ground_truth": rec.get("ground_truth")}


@router.post("/alerts/{tx_id}/review")
def review_alert(tx_id: str, body: ReviewIn, p: dict = Depends(require_analyst)):
    if not (body.action or body.label):
        raise HTTPException(422, "Provide an action and/or a label")
    rec = tx_record(tx_id)
    if not rec:
        raise HTTPException(404, "Transaction not found")
    prior = db.review_state().get(tx_id, {})
    with db.session_scope() as s:
        s.add(db.Review(transaction_id=tx_id, action=body.action, label=body.label, note=body.note, actor=p["actor"]))
    # A confirmed label on a LIVE transaction teaches the live feature store (once). Held-out snapshot rows were
    # already replayed into history, so they must not be counted twice.
    if body.label and not prior.get("label") and rec["source"] in ("live", "sim", "api"):
        with S.lock:
            S.store.apply_label(rec["customer_id"], rec["device_id"], rec["payment_id"], is_fraud=int(body.label == "FRAUD"))
    db.audit(p["actor"], "REVIEW", tx_id, {"action": body.action, "label": body.label})
    st = db.review_state()[tx_id]
    return {"transaction_id": tx_id, "status": status_of(st), "label": st["label"], "history": db.review_history(tx_id)}
