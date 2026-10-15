"""Health, live scoring, batch CSV scoring, scenario simulator."""
import io
import random
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.api.state import S, build_alerts, score_and_persist
from app.core import db
from app.core.risk_policy import classify
from app.core.schemas import PredictResponse, SimulateIn, TransactionIn
from app.core.security import require_analyst
from app.ml.feature_store import FEATURE_COLUMNS, FeatureStore
from app.ml.train import cost_of, evaluate

router = APIRouter()
BATCH_REQUIRED = {"customer_id", "amount", "device_id"}
CATEGORIES = ["Electronics", "Fashion", "Groceries", "Travel", "Home", "Beauty", "Sports", "Digital Goods"]
REGIONS = ["Chennai", "Mumbai", "Bengaluru", "Hyderabad", "Delhi", "Pune", "Kolkata", "Vijayawada"]


@router.get("/health")
def health():
    return {"status": "ok" if S.ready else "loading", "model": getattr(S, "manifest", {}).get("best_model")}


@router.post("/predict", response_model=PredictResponse)
def predict(tx: TransactionIn, p: dict = Depends(require_analyst)):
    if not S.ready:
        raise HTTPException(503, "Model not loaded yet")
    try:
        return score_and_persist(tx, p["actor"])
    except ValueError as e:
        raise HTTPException(409, str(e))


# ---- batch CSV ----------------------------------------------------------------------
@router.post("/predict/batch")
async def predict_batch(file: UploadFile = File(...), p: dict = Depends(require_analyst)):
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (20 MB max)")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        raise HTTPException(422, "Could not parse file as CSV")
    missing = BATCH_REQUIRED - set(df.columns)
    if missing:
        raise HTTPException(422, f"Missing required column(s): {', '.join(sorted(missing))}")
    if len(df) > 50000:
        raise HTTPException(413, "Too many rows (50,000 max)")

    warnings = []
    df = df.reset_index(drop=True)
    if "transaction_id" not in df:
        df["transaction_id"] = [f"BATCH-{i:06d}" for i in range(len(df))]
    for col, default in (("payment_id", None), ("account_age_days", 0), ("ip_region", "Unknown")):
        if col not in df:
            df[col] = default if default is not None else "UNKNOWN-" + df["customer_id"].astype(str)
            warnings.append(f"Column '{col}' missing; using a default")
    if "timestamp" in df:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        if df["timestamp"].isna().any():
            raise HTTPException(422, "Some timestamps could not be parsed")
    else:
        df["timestamp"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(range(len(df)), unit="min")
        warnings.append("No timestamp column; rows were treated as 1 minute apart (velocity features will be weak)")
    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    has_label = "is_fraud" in df

    store = FeatureStore(S.manifest.get("label_delay_days", 14))  # isolated: batch never touches live state
    feats = []
    for r in df.itertuples():
        feats.append(store.compute_and_update(
            r.timestamp, str(r.customer_id), str(r.device_id), str(r.payment_id), float(r.amount), float(r.account_age_days),
            str(r.ip_region), getattr(r, "merchant_category", None) if "merchant_category" in df else None,
            getattr(r, "payment_method", None) if "payment_method" in df else None,
            outcome=(int(r.is_fraud), 0, 0) if has_label else None))
    X = pd.DataFrame(feats)[FEATURE_COLUMNS]
    risk, anomaly = S.score_X(X)
    thr = S.threshold()
    levels = [classify(s, thr) for s in risk]
    out = df.copy()
    out["risk_score"], out["anomaly_score"] = risk.round(4), anomaly.round(4)
    out["risk_level"], out["decision"] = [l for l, _ in levels], [d for _, d in levels]

    summary = {"rows": len(out), "threshold": thr, "flagged": int((risk >= thr).sum()), "warnings": warnings,
               "by_level": out["risk_level"].value_counts().reindex(["LOW", "MEDIUM", "HIGH", "CRITICAL"], fill_value=0).to_dict()}
    if has_label and out["is_fraud"].nunique() > 1:
        pred = (risk >= thr).astype(int)
        fp_c, fn_c = db.get_costs()
        summary["metrics"] = evaluate(out["is_fraud"].astype(int).values, pred, risk)
        summary["cost"] = cost_of(out["is_fraud"].astype(int).values, pred, fp_c, fn_c)
    top = out.sort_values("risk_score", ascending=False).head(50)
    recs = [{"transaction_id": str(t.transaction_id), "customer_id": str(t.customer_id), "amount": float(t.amount),
             "risk_score": float(t.risk_score), "anomaly_score": float(t.anomaly_score), "timestamp": str(t.timestamp),
             "features": feats_row, "source": "batch"} for t, feats_row in zip(top.itertuples(), X.loc[top.index].to_dict("records"))]
    summary["top_alerts"] = build_alerts(recs, {})
    rid = uuid.uuid4().hex[:10]
    S.batches[rid] = out.to_csv(index=False)
    for old in list(S.batches)[:-10]:
        S.batches.pop(old)
    summary["result_id"] = rid
    db.audit(p["actor"], "BATCH_SCORE", detail={"rows": len(out), "flagged": summary["flagged"], "file": file.filename})
    return summary


@router.get("/predict/batch/{result_id}/download")
def download_batch(result_id: str, p: dict = Depends(require_analyst)):
    csv = S.batches.get(result_id)
    if csv is None:
        raise HTTPException(404, "Result expired or not found")
    return Response(csv, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=scored_{result_id}.csv"})


# ---- scenario simulator ----------------------------------------------------------------
def _payloads(scenario: str, n: int) -> list[TransactionIn]:
    rnd, tag, now = random.Random(), uuid.uuid4().hex[:6], db.utcnow()
    custs = list(S.customer_info.items())
    cid, info = rnd.choice(custs)
    out = []
    step = {"normal": 5, "velocity_burst": 20, "fraud_ring": 25, "multi_device_ring": 30, "account_takeover": 40}[scenario]

    def tx(i, **kw):
        out.append(TransactionIn(timestamp=now + pd.Timedelta(seconds=i * step).to_pytimedelta(), **kw))

    for i in range(n):
        if scenario == "normal":
            c, inf = rnd.choice(custs)
            tx(i, customer_id=c, amount=round(inf["avg"] * rnd.uniform(.7, 1.3), 2), device_id=inf["device"],
               payment_id=inf["payment"], account_age_days=inf["age"], ip_region=inf["region"])
        elif scenario == "velocity_burst":  # card testing: small probes from a brand-new account, then one big purchase
            tx(i, customer_id=f"SIM-{tag}-V", amount=round(rnd.uniform(60, 350) if i < n - 1 else rnd.uniform(3000, 8000), 2),
               device_id=f"SIM-DEV-{tag}-V", payment_id=f"SIM-PAY-{tag}-V", account_age_days=rnd.randint(0, 4),
               ip_region=rnd.choice(REGIONS), merchant_category=rnd.choice(CATEGORIES))
        elif scenario == "fraud_ring":
            tx(i, customer_id=f"SIM-{tag}-A{i:02d}", amount=round(5000 * rnd.uniform(.85, 1.15), 2), device_id=f"SIM-DEV-{tag}",
               payment_id=f"SIM-PAY-{tag}-{i:02d}", account_age_days=0, ip_region=rnd.choice(REGIONS), merchant_category="Digital Goods")
        elif scenario == "multi_device_ring":
            tx(i, customer_id=f"SIM-{tag}-M{i:02d}", amount=round(3500 * rnd.uniform(.7, 1.3), 2),
               device_id=f"SIM-DEV-{tag}-{rnd.randrange(4)}", payment_id=f"SIM-PAY-{tag}-{rnd.randrange(3)}",
               account_age_days=rnd.randint(0, 3), ip_region=rnd.choice(REGIONS), merchant_category=rnd.choice(["Electronics", "Digital Goods"]))
        else:  # account_takeover
            tx(i, customer_id=cid, amount=round(info["avg"] * rnd.uniform(2, 4), 2), device_id=f"SIM-DEV-ATO-{tag}",
               payment_id=info["payment"], account_age_days=info["age"],
               ip_region=rnd.choice([r for r in REGIONS if r != info["region"]]), merchant_category=rnd.choice(CATEGORIES))
    return out


@router.post("/simulate")
def simulate(body: SimulateIn, p: dict = Depends(require_analyst)):
    if not S.ready:
        raise HTTPException(503, "Model not loaded yet")
    results = []
    for tx in _payloads(body.scenario, body.n):
        r = score_and_persist(tx, p["actor"], source="sim")
        results.append({**r, "customer_id": tx.customer_id, "amount": tx.amount, "device_id": tx.device_id})
    return {"scenario": body.scenario, "results": results}
