from datetime import datetime, timedelta

import pandas as pd

from app.data.generate_dataset import generate_dataset
from app.ml.features import engineer_features
from app.ml.feature_store import FEATURE_COLUMNS, FeatureStore

T0 = datetime(2026, 6, 1, 12, 0)


def tx(store, ts, cust="C1", dev="D1", pay="P1", amount=500, outcome=None):
    return store.compute_and_update(ts, cust, dev, pay, amount, 100, "Chennai", "Fashion", "Card", outcome=outcome)


def test_labels_are_invisible_until_the_delay_has_passed():
    s = FeatureStore(label_delay_days=14)
    tx(s, T0, outcome=(1, 0, 1))                       # confirmed fraud + chargeback, but not known yet
    assert tx(s, T0 + timedelta(days=1), outcome=(1, 0, 1))["device_historical_fraud_rate"] == 0.0
    late = tx(s, T0 + timedelta(days=15))
    assert late["device_historical_fraud_rate"] == 1.0   # now both outcomes have matured
    assert late["customer_historical_chargebacks"] == 2


def test_features_never_depend_on_future_rows():
    raw = generate_dataset(n_customers=300, seed=3)
    short = engineer_features(raw.head(400))[FEATURE_COLUMNS]
    long = engineer_features(raw.head(900)).iloc[:400][FEATURE_COLUMNS]
    pd.testing.assert_frame_equal(short.reset_index(drop=True), long.reset_index(drop=True))


def test_first_transaction_has_no_history():
    f = tx(FeatureStore(), T0)
    assert f["customer_tx_count_30d"] == 0 and f["device_accounts_24h"] == 0 and f["tx_count_last_10min_cust"] == 0


def test_velocity_counts_only_prior_transactions():
    s = FeatureStore()
    tx(s, T0); tx(s, T0 + timedelta(minutes=2))
    assert tx(s, T0 + timedelta(minutes=4))["tx_count_last_10min_cust"] == 2
    assert tx(s, T0 + timedelta(hours=3))["tx_count_last_10min_cust"] == 0


def test_graph_features_grow_with_shared_device():
    s = FeatureStore()
    seen = [tx(s, T0 + timedelta(minutes=i), cust=f"C{i}", dev="SHARED", pay=f"P{i}")["graph_component_accounts"] for i in range(4)]
    assert seen == [1, 2, 3, 4]
    assert tx(s, T0 + timedelta(minutes=9), cust="LONER", dev="D9", pay="P9")["graph_component_accounts"] == 1


def test_live_label_feedback_updates_history():
    s = FeatureStore()
    tx(s, T0)
    s.apply_label("C1", "D1", "P1", is_fraud=1)
    assert tx(s, T0 + timedelta(hours=1))["customer_historical_fraud_rate"] == 1.0


def test_stats_and_batch_path_agree():
    raw = generate_dataset(n_customers=200, seed=5).head(300)
    batch = engineer_features(raw)[FEATURE_COLUMNS].reset_index(drop=True)
    s = FeatureStore()
    rows = [s.compute_and_update(r.timestamp, r.customer_id, r.device_id, r.payment_id, r.amount, r.account_age_days, r.ip_region,
                                 r.merchant_category, r.payment_method, outcome=(r.is_fraud, r.is_return, r.is_chargeback))
            for r in raw.assign(timestamp=pd.to_datetime(raw["timestamp"])).itertuples()]
    pd.testing.assert_frame_equal(batch, pd.DataFrame(rows)[FEATURE_COLUMNS])
