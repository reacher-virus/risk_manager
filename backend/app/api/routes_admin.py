"""Config (costs/threshold), audit log, drift monitoring, retraining."""
import threading

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.state import S
from app.core import db
from app.core.config import API_KEYS
from app.core.schemas import CostsIn, ThresholdIn
from app.core.security import principal, require_admin
from app.ml import drift

router = APIRouter()


@router.get("/config")
def get_config(p: dict = Depends(principal)):
    fp, fn = db.get_costs()
    return {"cost_fp": fp, "cost_fn": fn, "threshold": S.threshold(), "trained_threshold": S.manifest["chosen_threshold"],
            "label_delay_days": S.manifest.get("label_delay_days"), "role": p["role"], "auth_enabled": bool(API_KEYS)}


@router.put("/config/costs")
def set_costs(body: CostsIn, p: dict = Depends(require_admin)):
    db.set_setting("cost_fp", body.cost_fp)
    db.set_setting("cost_fn", body.cost_fn)
    db.audit(p["actor"], "CONFIG_COSTS", detail=body.model_dump())
    return get_config(p)


@router.put("/config/threshold")
def set_threshold(body: ThresholdIn, p: dict = Depends(require_admin)):
    with db.session_scope() as s:
        row = s.get(db.Setting, "threshold_override")
        if body.threshold is None and row:
            s.delete(row)
        elif body.threshold is not None:
            s.merge(db.Setting(key="threshold_override", value=str(body.threshold)))
    db.audit(p["actor"], "CONFIG_THRESHOLD", detail={"threshold": body.threshold})
    return get_config(p)


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=1000), action: str | None = None, p: dict = Depends(require_admin)):
    with db.session_scope() as s:
        q = select(db.AuditLog).order_by(db.AuditLog.id.desc()).limit(limit)
        if action:
            q = q.where(db.AuditLog.action == action)
        return [{"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "action": r.action, "transaction_id": r.transaction_id, "detail": r.detail}
                for r in s.execute(q).scalars()]


@router.get("/monitoring/summary")
def monitoring(p: dict = Depends(principal)):
    ref = S.manifest["drift_reference"]
    with db.session_scope() as s:
        rows = s.execute(select(db.ScoredTransaction.features, db.ScoredTransaction.risk_score)
                         .order_by(db.ScoredTransaction.created_at.desc()).limit(500)).all()
    if len(rows) >= 50:
        frame = pd.DataFrame([r[0] for r in rows]); scores = pd.Series([r[1] for r in rows])
        window = f"last {len(rows)} live-scored transactions vs training period"
    else:
        frame, scores = S.test_df, S.test_df["risk_score"]
        window = "held-out test period vs training period (fewer than 50 live transactions yet)"
    feats = sorted(({"feature": c, "psi": round(drift.psi(ref[c], frame[c]), 4)} for c in frame.columns if c in ref and c != "__score__"),
                   key=lambda r: r["psi"], reverse=True)
    for f in feats:
        f["status"] = drift.status(f["psi"])
    score_psi = round(drift.psi(ref["__score__"], scores), 4)
    rv = db.review_state()
    labels = [v["label"] for v in rv.values() if v["label"]]
    fb = {"labelled_cases": len(labels), "confirmed_fraud": labels.count("FRAUD"), "false_positives": labels.count("LEGIT"),
          "analyst_precision": round(labels.count("FRAUD") / len(labels), 4) if labels else None}
    return {"window": window, "score_psi": score_psi, "score_status": drift.status(score_psi), "features": feats[:15],
            "retrain_recommended": bool(score_psi > drift.PSI_RETRAIN or any(f["psi"] > drift.PSI_RETRAIN for f in feats)),
            "feedback": fb, "model": {"name": S.manifest["best_model"], "trained_at": S.manifest.get("trained_at"),
                                      "analyst_rows_in_training": S.manifest.get("analyst_rows", 0)}, "retrain": S.retrain}


def _retrain_job(actor: str):
    from app.ml import train
    S.retrain.update(state="running", started=db.utcnow().isoformat(), message=None)
    try:
        m = train.main(include_feedback=True)
        with S.lock:
            S.load_artifacts()
            S.load_frames()
        S.retrain.update(state="done", finished=db.utcnow().isoformat(), message=f"Retrained {m['best_model']} with {m['analyst_rows']} analyst-labelled rows")
        db.audit(actor, "RETRAIN_DONE", detail={"model": m["best_model"], "analyst_rows": m["analyst_rows"]})
    except Exception as e:  # pragma: no cover
        S.retrain.update(state="failed", finished=db.utcnow().isoformat(), message=str(e))
        db.audit(actor, "RETRAIN_FAILED", detail={"error": str(e)})


@router.post("/admin/retrain", status_code=202)
def retrain(p: dict = Depends(require_admin)):
    if S.retrain.get("state") == "running":
        raise HTTPException(409, "A retrain is already running")
    db.audit(p["actor"], "RETRAIN_STARTED")
    threading.Thread(target=_retrain_job, args=(p["actor"],), daemon=True).start()
    return {"state": "running"}


@router.get("/admin/retrain/status")
def retrain_status(p: dict = Depends(principal)):
    return S.retrain
