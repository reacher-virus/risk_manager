"""
Training + evaluation pipeline.

  * Chronological 70/15/15 split; the test set is evaluated exactly once.
  * Candidates: logistic regression, random forest, XGBoost -> best by validation PR-AUC.
  * Probability calibration (isotonic) on the FIRST half of validation.
  * Cost-optimal threshold chosen on the SECOND half of validation (never on test).
  * Isolation-forest anomaly layer + drift reference stored for monitoring.

Run:  python -m app.ml.train
"""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import COST_FN, COST_FP, LABEL_DELAY_DAYS, MODEL_DIR, PROCESSED_PATH, WARMUP_DAYS
from app.ml.anomaly import AnomalyDetector
from app.ml.drift import build_reference
from app.ml.feature_store import FEATURE_COLUMNS
from app.ml.rule_baseline import rule_based_predict, rule_based_score

try:
    from xgboost import XGBClassifier
except ImportError:  # pragma: no cover
    XGBClassifier = None


def chronological_split(df: pd.DataFrame, warmup_days: float = WARMUP_DAYS):
    """70/15/15 by time, after dropping the warm-up window (history + labels not yet available)."""
    df = df.sort_values("timestamp").reset_index(drop=True)
    if warmup_days:
        df = df[df["timestamp"] >= df["timestamp"].iloc[0] + pd.Timedelta(days=warmup_days)].reset_index(drop=True)
    n = len(df)
    return df.iloc[:int(n * .70)], df.iloc[int(n * .70):int(n * .85)], df.iloc[int(n * .85):]


def evaluate(y_true, y_pred, y_score) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {"precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
            "pr_auc": round(float(average_precision_score(y_true, y_score)), 4),
            "roc_auc": round(float(roc_auc_score(y_true, y_score)), 4) if len(set(y_true)) > 1 else None,
            "false_positive_rate": round(float(fp / (fp + tn)) if (fp + tn) else 0.0, 4),
            "true_positives": int(tp), "false_positives": int(fp), "true_negatives": int(tn), "false_negatives": int(fn)}


def cost_of(y_true, y_pred, cost_fp=COST_FP, cost_fn=COST_FN) -> dict:
    _, fp, fn, _ = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {"fp": int(fp), "fn": int(fn), "cost_fp_total": int(fp * cost_fp), "cost_fn_total": int(fn * cost_fn),
            "total_cost": int(fp * cost_fp + fn * cost_fn)}


def sweep_thresholds(y_true, y_score, cost_fp=COST_FP, cost_fn=COST_FN, thresholds=None) -> pd.DataFrame:
    y_true = np.asarray(y_true)
    thresholds = np.round(np.arange(0.01, 0.99, 0.01), 2) if thresholds is None else thresholds
    rows = []
    for t in thresholds:
        pred = (np.asarray(y_score) >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum()); fp = int(((pred == 1) & (y_true == 0)).sum())
        fn = int(((pred == 0) & (y_true == 1)).sum())
        rows.append({"threshold": float(t), "precision": tp / (tp + fp) if tp + fp else 0.0,
                     "recall": tp / (tp + fn) if tp + fn else 0.0, "fp": fp, "fn": fn,
                     "total_cost": fp * cost_fp + fn * cost_fn})
    return pd.DataFrame(rows)


def pick_threshold(sweep: pd.DataFrame, tolerance: float = 0.03) -> float:
    """Highest threshold whose expected cost is within `tolerance` of the minimum. Noisy cost curves often
    have many near-ties; preferring the higher one means fewer legitimate customers get flagged."""
    best = sweep["total_cost"].min()
    ok = sweep[sweep["total_cost"] <= best * (1 + tolerance)]
    return float(ok["threshold"].max())


def feedback_training_rows() -> pd.DataFrame:
    """Analyst-labelled live transactions (appended to the TRAIN split only)."""
    try:
        from app.core import db
        return db.feedback_training_rows()
    except Exception:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["is_fraud"])


def main(include_feedback: bool = False) -> dict:
    df = pd.read_csv(PROCESSED_PATH, parse_dates=["timestamp"])
    train, val, test = chronological_split(df)
    extra = feedback_training_rows() if include_feedback else pd.DataFrame()
    if len(extra):
        train = pd.concat([train, extra[FEATURE_COLUMNS + ["is_fraud"]]], ignore_index=True)
    print(f"Split -> train {len(train):,} (+{len(extra)} analyst-labelled) | val {len(val):,} | test {len(test):,}")
    print(f"Fraud rate -> train {train.is_fraud.mean():.3%} val {val.is_fraud.mean():.3%} test {test.is_fraud.mean():.3%}")

    Xtr, ytr = train[FEATURE_COLUMNS], train["is_fraud"]
    Xv, yv = val[FEATURE_COLUMNS], val["is_fraud"]
    Xte, yte = test[FEATURE_COLUMNS], test["is_fraud"]
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))

    candidates = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=5,
                                                class_weight="balanced_subsample", n_jobs=-1, random_state=42),
    }
    if XGBClassifier:
        candidates["xgboost"] = XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.08, subsample=0.8,
                                              colsample_bytree=0.8, scale_pos_weight=spw, eval_metric="aucpr",
                                              random_state=42, n_jobs=-1)
    val_pr = {}
    for name, m in candidates.items():
        m.fit(Xtr, ytr)
        val_pr[name] = float(average_precision_score(yv, m.predict_proba(Xv)[:, 1]))
        print(f"  [val] {name}: PR-AUC {val_pr[name]:.4f}")
    best_name = max(val_pr, key=val_pr.get)
    base = candidates[best_name]
    print(f"Best on validation PR-AUC: {best_name}")

    # calibration on first half of validation, threshold on second half
    half = len(val) // 2
    val_cal, val_thr = val.iloc[:half], val.iloc[half:]
    method = "isotonic" if int(val_cal.is_fraud.sum()) >= 50 else "sigmoid"
    calibrated = CalibratedClassifierCV(FrozenEstimator(base), method=method).fit(val_cal[FEATURE_COLUMNS], val_cal["is_fraud"])

    sweep = sweep_thresholds(val_thr["is_fraud"], calibrated.predict_proba(val_thr[FEATURE_COLUMNS])[:, 1])
    threshold = pick_threshold(sweep)
    print(f"Calibration: {method} | cost-optimal threshold (validation, FP={COST_FP} FN={COST_FN}): {threshold}")

    # single held-out test evaluation
    raw_te = base.predict_proba(Xte)[:, 1]
    cal_te = calibrated.predict_proba(Xte)[:, 1]
    pred = (cal_te >= threshold).astype(int)
    ml_metrics, ml_cost = evaluate(yte.values, pred, cal_te), cost_of(yte.values, pred)
    rule_pred, rule_score = rule_based_predict(test), rule_based_score(test)
    rule_metrics, rule_cost = evaluate(yte.values, rule_pred.values, rule_score.values), cost_of(yte.values, rule_pred.values)
    ml_metrics["brier_uncalibrated"] = round(float(brier_score_loss(yte, raw_te)), 5)
    ml_metrics["brier_calibrated"] = round(float(brier_score_loss(yte, cal_te)), 5)
    print("\n=== HELD-OUT TEST (evaluated once) ===")
    print("ML  :", json.dumps(ml_metrics)); print("cost:", json.dumps(ml_cost))
    print("Rule:", json.dumps(rule_metrics)); print("cost:", json.dumps(rule_cost))

    anomaly = AnomalyDetector().fit(Xtr)
    final = base[-1] if hasattr(base, "named_steps") else base
    imp = (final.feature_importances_ if hasattr(final, "feature_importances_") else np.abs(final.coef_[0]))
    drift_ref = build_reference(train, FEATURE_COLUMNS)
    drift_ref["__score__"] = build_reference(pd.DataFrame({"s": calibrated.predict_proba(Xv)[:, 1]}), ["s"])["s"]

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated, MODEL_DIR / "model.joblib")
    joblib.dump(base, MODEL_DIR / "model_base.joblib")
    joblib.dump(anomaly, MODEL_DIR / "anomaly.joblib")
    manifest = {
        "best_model": best_name, "calibration": method, "chosen_threshold": threshold,
        "feature_columns": FEATURE_COLUMNS, "feature_importances": dict(zip(FEATURE_COLUMNS, map(float, imp))),
        "val_pr_auc_by_model": val_pr, "test_metrics_ml": ml_metrics, "test_cost_ml": ml_cost,
        "test_metrics_rule_baseline": rule_metrics, "test_cost_rule_baseline": rule_cost,
        "cost_fp": COST_FP, "cost_fn": COST_FN, "label_delay_days": LABEL_DELAY_DAYS,
        "trained_rows": int(len(train)), "analyst_rows": int(len(extra)), "drift_reference": drift_ref,
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
        "dataset_note": ("Synthetic dataset (app/data/generate_dataset.py). Metrics describe simulated ground truth, "
                         "not a production benchmark."),
    }
    (MODEL_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nSaved artifacts to {MODEL_DIR}")
    return manifest


if __name__ == "__main__":
    import sys
    main(include_feedback="--include-feedback" in sys.argv)
