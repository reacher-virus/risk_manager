"""Drift monitoring via Population Stability Index (PSI). Rule of thumb: <0.1 stable, 0.1-0.25 watch, >0.25 retrain."""
import numpy as np

PSI_WATCH, PSI_RETRAIN = 0.10, 0.25


def build_reference(df, columns, bins: int = 10) -> dict:
    ref = {}
    for col in columns:
        x = df[col].to_numpy(dtype=float)
        edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
        if len(edges) < 2:
            continue
        ref[col] = {"edges": edges.tolist(), "props": _props(x, edges).tolist()}
    return ref


def _props(x, edges):
    idx = np.searchsorted(np.asarray(edges)[1:-1], x, side="right")
    counts = np.bincount(idx, minlength=len(edges) - 1).astype(float)
    return counts / max(counts.sum(), 1.0)


def psi(ref_entry: dict, values) -> float:
    e = np.clip(np.asarray(ref_entry["props"]), 1e-4, None)
    a = np.clip(_props(np.asarray(values, dtype=float), ref_entry["edges"]), 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def status(value: float) -> str:
    return "retrain" if value > PSI_RETRAIN else "watch" if value > PSI_WATCH else "stable"
