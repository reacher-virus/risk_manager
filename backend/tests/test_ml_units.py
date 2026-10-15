import numpy as np
import pandas as pd

from app.core.risk_policy import classify, cutoffs, min_score_for
from app.ml import drift
from app.ml.graph import detect_rings, ring_graph
from app.ml.train import chronological_split, cost_of, pick_threshold, sweep_thresholds


def test_policy_bands_follow_threshold_and_are_monotonic():
    c = cutoffs(0.2)
    assert c["MEDIUM"] == 0.1 and c["HIGH"] == 0.2 and c["CRITICAL"] == 0.5
    order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    levels = [order.index(classify(s, 0.2)[0]) for s in np.linspace(0, 1, 50)]
    assert levels == sorted(levels)
    assert classify(0.19, 0.2)[1] == "MONITOR" and classify(0.2, 0.2)[1] == "REVIEW" and classify(0.99, 0.2)[1] == "HOLD_FOR_VERIFICATION"
    assert min_score_for("HIGH", 0.2) == 0.2 and min_score_for("LOW", 0.2) == 0.0


def test_cost_sweep_matches_hand_calculation():
    y, s = np.array([1, 1, 0, 0, 0]), np.array([0.9, 0.4, 0.6, 0.2, 0.1])
    row = sweep_thresholds(y, s, 10, 100, thresholds=[0.5]).iloc[0]
    assert (row["fp"], row["fn"], row["total_cost"]) == (1, 1, 110)
    assert cost_of(y, (s >= 0.5).astype(int), 10, 100)["total_cost"] == 110


def test_pick_threshold_prefers_higher_when_costs_nearly_tie():
    sweep = pd.DataFrame({"threshold": [0.1, 0.2, 0.3, 0.9], "total_cost": [1000, 1020, 1025, 5000]})
    assert pick_threshold(sweep) == 0.3


def test_split_is_chronological_non_overlapping_and_drops_warmup():
    ts = pd.date_range("2026-05-01", periods=1000, freq="2h")
    df = pd.DataFrame({"timestamp": ts, "x": range(1000)})
    tr, va, te = chronological_split(df, warmup_days=14)
    assert tr["timestamp"].max() <= va["timestamp"].min() and va["timestamp"].max() <= te["timestamp"].min()
    assert tr["timestamp"].min() >= ts[0] + pd.Timedelta(days=14)
    assert len(tr) + len(va) + len(te) == len(df[df["timestamp"] >= ts[0] + pd.Timedelta(days=14)])


def test_psi_is_near_zero_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    base = pd.DataFrame({"a": rng.normal(0, 1, 5000)})
    ref = drift.build_reference(base, ["a"])["a"]
    assert drift.psi(ref, rng.normal(0, 1, 5000)) < 0.05
    assert drift.psi(ref, rng.normal(2, 1, 5000)) > drift.PSI_RETRAIN


def _ring_df():
    rows = [(f"C{i}", "DEV-X", f"P{i}") for i in range(4)] + [("LONE", "DEV-Y", "P-LONE")]
    df = pd.DataFrame(rows, columns=["customer_id", "device_id", "payment_id"])
    return df.assign(amount=100.0, timestamp=pd.Timestamp("2026-07-01"), risk_score=[.9, .8, .95, .85, .01])


def test_ring_detection_finds_shared_device_network_and_ignores_loners():
    rings = detect_rings(_ring_df(), min_accounts=3)
    assert len(rings) == 1 and rings[0]["accounts"] == 4 and rings[0]["devices"] == 1 and rings[0]["cards"] == 4
    g = ring_graph(_ring_df(), rings[0]["ring_id"])
    assert len(g["nodes"]) == 9 and len(g["edges"]) == 8
    assert ring_graph(_ring_df(), "RING-nope") is None
