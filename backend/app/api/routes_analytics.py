"""Dashboard summary, metrics, charts, threshold/cost analysis, network graph."""
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sklearn.metrics import average_precision_score, precision_recall_curve

from app.api.rings import get_ring_graph, get_rings
from app.api.state import S, status_of
from app.core import db
from app.core.risk_policy import cutoffs
from app.core.security import principal
from app.ml.train import cost_of, evaluate, pick_threshold, sweep_thresholds

router = APIRouter()


def _split(name: str) -> pd.DataFrame:
    if name not in ("val", "test"):
        raise HTTPException(422, "split must be 'val' or 'test'")
    return S.val_df if name == "val" else S.test_df


def _at(df: pd.DataFrame, thr: float) -> tuple[dict, dict]:
    y, s = df["is_fraud"].values, df["risk_score"].values
    pred = (s >= thr).astype(int)
    fp_c, fn_c = db.get_costs()
    return evaluate(y, pred, s), cost_of(y, pred, fp_c, fn_c)


@router.get("/dashboard/summary")
def dashboard_summary(p: dict = Depends(principal)):
    thr, df = S.threshold(), S.test_df
    c = cutoffs(thr)
    m, cost = _at(df, thr)
    fp_c, _ = db.get_costs()
    fraud_amt = float(df.loc[df["is_fraud"] == 1, "amount"].mean()) if (df["is_fraud"] == 1).any() else 0.0
    comb, rv = S.combined_df(), db.review_state()
    flagged = comb[comb["risk_score"] >= thr]
    live = comb[comb["source"] != "test"]
    return {"transactions_analyzed": int(len(df)), "suspicious_transactions": int((df["risk_score"] >= c["MEDIUM"]).sum()),
            "high_risk_transactions": int((df["risk_score"] >= thr).sum()),
            "estimated_loss_prevented": round(m["true_positives"] * fraud_amt - m["false_positives"] * fp_c, 2),
            "precision": m["precision"], "recall": m["recall"], "pr_auc": m["pr_auc"],
            "false_positive_rate": m["false_positive_rate"], "threshold": thr,
            "live_scored": int(len(live)), "live_flagged": int((live["risk_score"] >= thr).sum()),
            "open_alerts": int(sum(status_of(rv.get(t)) == "NEW" for t in flagged["transaction_id"]))}


@router.get("/metrics")
def metrics(p: dict = Depends(principal)):
    m, thr = S.manifest, S.threshold()
    tm, cost = _at(S.test_df, thr)
    return {"model_name": m["best_model"], "threshold": thr, "trained_threshold": m["chosen_threshold"],
            "calibration": m["calibration"], **{k: tm[k] for k in ("precision", "recall", "f1", "pr_auc", "roc_auc", "false_positive_rate")},
            "brier_calibrated": m["test_metrics_ml"].get("brier_calibrated"), "brier_uncalibrated": m["test_metrics_ml"].get("brier_uncalibrated"),
            "trained_at": m.get("trained_at"), "label_delay_days": m.get("label_delay_days"), "dataset_note": m["dataset_note"],
            "val_pr_auc_by_model": m["val_pr_auc_by_model"]}


@router.get("/model-comparison")
def model_comparison(p: dict = Depends(principal)):
    m, fp_c, fn_c = S.manifest, *db.get_costs()
    ml, _ = _at(S.test_df, S.threshold())
    rule = m["test_metrics_rule_baseline"]

    def side(x):
        return {"precision": x["precision"], "recall": x["recall"], "f1": x["f1"], "pr_auc": x["pr_auc"],
                "fp": x["false_positives"], "fn": x["false_negatives"],
                "fp_cost": x["false_positives"] * fp_c, "fn_cost": x["false_negatives"] * fn_c}
    r, a = side(rule), side(ml)
    total_r, total_a = r["fp_cost"] + r["fn_cost"], a["fp_cost"] + a["fn_cost"]
    return {"rule_based": r, "ml_model": a, "model_name": m["best_model"], "cost_reduction_pct": round((1 - total_a / total_r) * 100, 1) if total_r else 0.0}


# ---- charts -----------------------------------------------------------------------------
@router.get("/analytics/timeseries")
def timeseries(bucket: str = Query("day", pattern="^(day|hour)$"), p: dict = Depends(principal)):
    df, thr = S.combined_df().copy(), S.threshold()
    df["bucket"] = df["timestamp"].dt.floor("D" if bucket == "day" else "h")
    g = df.groupby("bucket")
    out = pd.DataFrame({"transactions": g.size(), "flagged": g["risk_score"].apply(lambda s: int((s >= thr).sum())),
                        "mean_risk": g["risk_score"].mean().round(4), "synthetic_fraud": g["is_fraud"].sum()}).reset_index()
    out["bucket"] = out["bucket"].astype(str)
    return out.fillna(0).to_dict("records")


@router.get("/analytics/breakdown")
def breakdown(by: str = Query("ip_region", pattern="^(ip_region|merchant_category|payment_method)$"), p: dict = Depends(principal)):
    df, thr = S.combined_df().copy(), S.threshold()
    df["flag"] = (df["risk_score"] >= thr).astype(int)
    g = df.dropna(subset=[by]).groupby(by)
    out = pd.DataFrame({"transactions": g.size(), "flagged": g["flag"].sum(), "flag_rate": g["flag"].mean().round(4),
                        "avg_risk": g["risk_score"].mean().round(4), "synthetic_fraud_rate": g["is_fraud"].mean().round(4)}).reset_index()
    return out.rename(columns={by: "name"}).fillna(0).sort_values("flag_rate", ascending=False).to_dict("records")


@router.get("/analytics/pr-curve")
def pr_curve(split: str = "test", p: dict = Depends(principal)):
    df = _split(split)
    pr, rc, th = precision_recall_curve(df["is_fraud"], df["risk_score"])
    idx = np.unique(np.linspace(0, len(pr) - 1, 120).astype(int))
    pts = [{"recall": round(float(rc[i]), 4), "precision": round(float(pr[i]), 4), "threshold": round(float(th[min(i, len(th) - 1)]), 4)} for i in idx]
    return {"split": split, "average_precision": round(float(average_precision_score(df["is_fraud"], df["risk_score"])), 4),
            "base_rate": round(float(df["is_fraud"].mean()), 4), "points": pts}


@router.get("/analytics/confusion")
def confusion(threshold: float | None = Query(None, gt=0, lt=1), split: str = "test", p: dict = Depends(principal)):
    thr = threshold or S.threshold()
    m, _ = _at(_split(split), thr)
    return {"split": split, "threshold": thr, **{k: m[k] for k in ("true_positives", "false_positives", "true_negatives", "false_negatives",
                                                                  "precision", "recall", "false_positive_rate")}}


@router.get("/analysis/threshold")
def threshold_analysis(threshold: float | None = Query(None, gt=0, lt=1), cost_fp: float | None = Query(None, gt=0),
                       cost_fn: float | None = Query(None, gt=0), split: str = "test", p: dict = Depends(principal)):
    """Interactive cost curve: what happens if the threshold / business costs change."""
    df, thr = _split(split), threshold or S.threshold()
    d_fp, d_fn = db.get_costs()
    fp_c, fn_c = cost_fp or d_fp, cost_fn or d_fn
    y, s = df["is_fraud"].values, df["risk_score"].values
    pred = (s >= thr).astype(int)
    m, c = evaluate(y, pred, s), cost_of(y, pred, fp_c, fn_c)
    sweep = sweep_thresholds(y, s, fp_c, fn_c)
    best = pick_threshold(sweep)
    return {"split": split, "threshold": thr, "cost_fp": fp_c, "cost_fn": fn_c, "metrics": m, "cost": c,
            "cost_if_no_model": int(y.sum() * fn_c), "optimal_threshold": best,
            "optimal_cost": int(sweep.loc[sweep["threshold"] == best, "total_cost"].iloc[0]),
            "sweep": sweep.iloc[::2].round(4).to_dict("records")}


# ---- network graph ---------------------------------------------------------------------------
@router.get("/graph/rings")
def rings(min_accounts: int = Query(3, ge=2, le=20), limit: int = Query(30, ge=1, le=200), p: dict = Depends(principal)):
    allr = get_rings(min_accounts)
    return {"total": len(allr), "rings": allr[:limit]}


@router.get("/graph/rings/{ring_id}")
def ring_detail(ring_id: str, p: dict = Depends(principal)):
    g = get_ring_graph(ring_id)
    if not g:
        raise HTTPException(404, "Ring not found")
    g["summary"] = next((r for r in get_rings(3) if r["ring_id"] == ring_id), None)
    return g
