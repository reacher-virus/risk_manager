"""Batch feature engineering for training: replays history through the shared FeatureStore."""
import pandas as pd

from app.core.config import PROCESSED_PATH, RAW_PATH
from app.ml.feature_store import FEATURE_COLUMNS, FeatureStore

__all__ = ["engineer_features", "FEATURE_COLUMNS"]


def engineer_features(df: pd.DataFrame, label_delay_days: float | None = None) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    assert df["timestamp"].is_monotonic_increasing, "Input must be sorted chronologically"
    store = FeatureStore() if label_delay_days is None else FeatureStore(label_delay_days)
    has = {c: c in df.columns for c in ("is_return", "is_chargeback", "merchant_category", "payment_method")}
    rows = []
    for r in df.itertuples():
        rows.append(store.compute_and_update(
            ts=r.timestamp, customer_id=r.customer_id, device_id=r.device_id, payment_id=r.payment_id,
            amount=r.amount, account_age_days=r.account_age_days, ip_region=r.ip_region,
            merchant_category=r.merchant_category if has["merchant_category"] else None,
            payment_method=r.payment_method if has["payment_method"] else None,
            outcome=(r.is_fraud, r.is_return if has["is_return"] else 0, r.is_chargeback if has["is_chargeback"] else 0)))
    feats = pd.DataFrame(rows)
    # `amount` is both a raw column and a model feature (identical values); keep a single copy.
    return pd.concat([df.reset_index(drop=True), feats.drop(columns=[c for c in feats if c in df.columns])], axis=1)


if __name__ == "__main__":
    out = engineer_features(pd.read_csv(RAW_PATH))
    out.to_csv(PROCESSED_PATH, index=False)
    print(f"Engineered {len(FEATURE_COLUMNS)} features for {len(out):,} rows -> {PROCESSED_PATH}")
