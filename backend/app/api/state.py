"""Shared application state + the single scoring path used by /predict, /simulate and batch."""
import json
import threading
import uuid

import joblib
import numpy as np
import pandas as pd

from app.core import db, webhook
from app.core.config import MODEL_DIR, PROCESSED_PATH, RAW_PATH
from app.core.risk_policy import classify, min_score_for
from app.core.schemas import TransactionIn
from app.ml.explain import Explainer
from app.ml.feature_store import FEATURE_COLUMNS, FeatureStore
from app.ml.train import chronological_split

META_COLS = ["transaction_id", "customer_id", "device_id", "payment_id", "amount", "timestamp", "ip_region",
             "merchant_category", "payment_method", "account_age_days"]


class AppState:
    def __init__(self):
        self.lock = threading.RLock()
        self.ready = False
        self.batches: dict = {}
        self.retrain = {"state": "idle"}
        self.store: FeatureStore | None = None
        self._combined = (None, None)

    # ---- artifacts ---------------------------------------------------------------
    def load_artifacts(self):
        self.model = joblib.load(MODEL_DIR / "model.joblib")
        self.base = joblib.load(MODEL_DIR / "model_base.joblib")
        self.anomaly = joblib.load(MODEL_DIR / "anomaly.joblib")
        self.manifest = json.loads((MODEL_DIR / "manifest.json").read_text())
        self.explainer = Explainer(self.base, self.manifest.get("feature_importances"))

    def load_frames(self):
        df = pd.read_csv(PROCESSED_PATH, parse_dates=["timestamp"])
        _, val, test = chronological_split(df)
        out = []
        for part in (val, test):
            part = part.reset_index(drop=True).copy()
            X = part[FEATURE_COLUMNS]
            part["risk_score"] = self.model.predict_proba(X)[:, 1]
            part["anomaly_score"] = self.anomaly.score(X)
            part["source"] = "test"
            out.append(part)
        self.val_df, self.test_df = out
        self.test_index = {t: i for i, t in enumerate(self.test_df["transaction_id"])}
        self._combined = (None, None)

    def seed_store(self):
        raw = pd.read_csv(RAW_PATH, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        store = FeatureStore(self.manifest.get("label_delay_days", 14))
        has_ret, has_cb = "is_return" in raw, "is_chargeback" in raw
        for r in raw.itertuples():
            store.compute_and_update(r.timestamp, r.customer_id, r.device_id, r.payment_id, r.amount, r.account_age_days,
                                     r.ip_region, getattr(r, "merchant_category", None), getattr(r, "payment_method", None),
                                     outcome=(r.is_fraud, r.is_return if has_ret else 0, r.is_chargeback if has_cb else 0))
        self.store = store
        legit = raw[raw["fraud_pattern"] == "none"]
        g = legit.groupby("customer_id")
        info = g.agg(device=("device_id", "last"), payment=("payment_id", "last"), region=("ip_region", "last"),
                     avg=("amount", "mean"), age=("account_age_days", "last"), n=("amount", "size"))
        self.customer_info = info[info["n"] >= 8].to_dict("index")

    def load_all(self):
        db.init_db()
        self.load_artifacts()
        self.load_frames()
        self.seed_store()
        self.ready = True

    # ---- helpers -------------------------------------------------------------------
    def threshold(self) -> float:
        override = db.get_setting("threshold_override")
        return float(override) if override else float(self.manifest["chosen_threshold"])

    def score_X(self, X: pd.DataFrame):
        return self.model.predict_proba(X[FEATURE_COLUMNS])[:, 1], self.anomaly.score(X[FEATURE_COLUMNS])

    def combined_df(self) -> pd.DataFrame:
        """Held-out test rows + live-scored rows (cached until the live row count changes)."""
        live = db.live_dataframe()
        if self._combined[0] == len(live):
            return self._combined[1]
        cols = META_COLS[:-1] + ["risk_score", "anomaly_score", "is_fraud", "source"]
        df = pd.concat([self.test_df[cols], live[cols]], ignore_index=True)
        self._combined = (len(live), df)
        return df


S = AppState()


def status_of(rv: dict | None) -> str:
    return {"APPROVE": "APPROVED", "HOLD": "HELD", "ESCALATE": "ESCALATED"}.get((rv or {}).get("action"), "NEW")


def tx_record(tx_id: str) -> dict | None:
    """Unified record from the live DB or the held-out snapshot."""
    with db.session_scope() as s:
        t = s.get(db.ScoredTransaction, tx_id)
        if t:
            return {"transaction_id": t.transaction_id, "customer_id": t.customer_id, "device_id": t.device_id,
                    "payment_id": t.payment_id, "amount": t.amount, "timestamp": t.ts.isoformat(), "ip_region": t.ip_region,
                    "merchant_category": t.merchant_category, "payment_method": t.payment_method,
                    "account_age_days": t.account_age_days, "risk_score": t.risk_score, "anomaly_score": t.anomaly_score,
                    "features": t.features, "source": t.source or "live"}
    i = S.test_index.get(tx_id)
    if i is None:
        return None
    r = S.test_df.iloc[i]
    return {**{k: (str(r[k]) if k == "timestamp" else (r[k].item() if hasattr(r[k], "item") else r[k])) for k in META_COLS},
            "risk_score": float(r["risk_score"]), "anomaly_score": float(r["anomaly_score"]),
            "features": {k: float(r[k]) for k in FEATURE_COLUMNS}, "source": "test",
            "ground_truth": {"is_fraud": int(r["is_fraud"]), "fraud_pattern": r["fraud_pattern"], "synthetic": True}}


def build_alerts(records: list[dict], reviews: dict) -> list[dict]:
    """Attach level/decision/reasons/status to records, using one batched SHAP call."""
    if not records:
        return []
    X = pd.DataFrame([r["features"] for r in records])[FEATURE_COLUMNS]
    contrib = S.explainer.contributions(X)
    thr, out = S.threshold(), []
    for i, r in enumerate(records):
        level, decision = classify(r["risk_score"], thr)
        reasons, contribs = S.explainer.explain_row(r["features"], None if contrib is None else contrib[i])
        rv = reviews.get(r["transaction_id"])
        out.append({"transaction_id": r["transaction_id"], "customer_id": r["customer_id"], "amount": float(r["amount"]),
                    "risk_score": round(float(r["risk_score"]), 4), "risk_level": level, "decision": decision,
                    "reasons": reasons, "contributions": contribs, "anomaly_score": round(float(r["anomaly_score"]), 4),
                    "timestamp": str(r["timestamp"]), "source": r["source"], "status": status_of(rv),
                    "label": (rv or {}).get("label")})
    return out


def score_and_persist(tx: TransactionIn, actor: str, source: str = "api") -> dict:
    """The one live scoring path: features -> calibrated score -> anomaly -> explanation -> DB + audit."""
    tx_id = tx.transaction_id or f"TX-LIVE-{uuid.uuid4().hex[:10]}"
    with db.session_scope() as s:
        if s.get(db.ScoredTransaction, tx_id):
            raise ValueError(f"transaction_id {tx_id} already exists")
    with S.lock:
        ts = tx.timestamp.replace(tzinfo=None) if tx.timestamp else db.utcnow()
        if S.store.last_ts is not None and ts < S.store.last_ts:
            ts = S.store.last_ts  # feature windows require non-decreasing time
        payment = tx.payment_id or f"UNKNOWN-{tx.customer_id}"
        feats = S.store.compute_and_update(ts, tx.customer_id, tx.device_id, payment, tx.amount, tx.account_age_days,
                                           tx.ip_region or "Unknown", tx.merchant_category, tx.payment_method)
    X = pd.DataFrame([feats])[FEATURE_COLUMNS]
    risk, anomaly = (float(a[0]) for a in S.score_X(X))
    thr = S.threshold()
    level, decision = classify(risk, thr)
    contrib = S.explainer.contributions(X)
    reasons, contribs = S.explainer.explain_row(feats, None if contrib is None else contrib[0], n_contrib=6)
    novel = bool(anomaly >= 0.99 and risk < thr)
    if novel:
        reasons = reasons + ["Behaviour is highly unusual compared with normal traffic (anomaly layer)"]
    with db.session_scope() as s:
        s.add(db.ScoredTransaction(transaction_id=tx_id, customer_id=tx.customer_id, device_id=tx.device_id, payment_id=payment,
                                   amount=tx.amount, ip_region=tx.ip_region, merchant_category=tx.merchant_category,
                                   payment_method=tx.payment_method, account_age_days=tx.account_age_days, ts=ts,
                                   risk_score=risk, anomaly_score=anomaly, risk_level=level, decision=decision,
                                   reasons=reasons, features=feats, source=source))
    db.audit(actor, "PREDICT" if source == "api" else f"PREDICT_{source.upper()}", tx_id,
             {"risk_score": round(risk, 4), "decision": decision, "threshold": thr})
    if level == "CRITICAL":
        webhook.notify_critical(tx_id, tx.customer_id, tx.amount, round(risk, 4), decision)   # SSRF-guarded, best effort
    return {"transaction_id": tx_id, "risk_score": round(risk, 4), "risk_level": level, "decision": decision,
            "reasons": reasons, "contributions": contribs[:5], "anomaly_score": round(anomaly, 4), "novel_pattern": novel}
