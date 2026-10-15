"""Ring detection: connected components over customer-device-card links (NetworkX)."""
import hashlib

import networkx as nx
import numpy as np
import pandas as pd


def _graph(df: pd.DataFrame) -> nx.Graph:
    g = nx.Graph()
    for cu, de, pa in df[["customer_id", "device_id", "payment_id"]].drop_duplicates().itertuples(index=False):
        g.add_edge(f"c:{cu}", f"d:{de}")
        g.add_edge(f"c:{cu}", f"p:{pa}")
    return g


def ring_id_for(nodes) -> str:
    return "RING-" + hashlib.md5(sorted(nodes)[0].encode()).hexdigest()[:8]


def detect_rings(df: pd.DataFrame, min_accounts: int = 3) -> list[dict]:
    """Return suspicious account networks ranked by average risk. `df` needs customer/device/payment ids,
    amount, timestamp and risk_score; `is_fraud` is optional (synthetic ground truth)."""
    if df.empty:
        return []
    comps = [c for c in nx.connected_components(_graph(df)) if sum(n.startswith("c:") for n in c) >= min_accounts]
    owner = {n[2:]: i for i, comp in enumerate(comps) for n in comp if n.startswith("c:")}
    sub = df[df["customer_id"].isin(owner)].copy()
    sub["_comp"] = sub["customer_id"].map(owner)
    out = []
    for i, g in sub.groupby("_comp"):
        comp = comps[i]
        r = {"ring_id": ring_id_for(comp),
             "accounts": int(sum(n.startswith("c:") for n in comp)),
             "devices": int(sum(n.startswith("d:") for n in comp)),
             "cards": int(sum(n.startswith("p:") for n in comp)),
             "transactions": int(len(g)), "total_amount": float(g["amount"].sum()),
             "avg_risk": float(g["risk_score"].mean()), "max_risk": float(g["risk_score"].max()),
             "first_seen": str(g["timestamp"].min()), "last_seen": str(g["timestamp"].max())}
        if "is_fraud" in g and g["is_fraud"].notna().any():
            r["synthetic_fraud_rate"] = float(g["is_fraud"].dropna().mean())
        out.append(r)
    out.sort(key=lambda r: (r["avg_risk"], r["accounts"]), reverse=True)
    return out


def ring_graph(df: pd.DataFrame, ring_id: str, min_accounts: int = 3) -> dict | None:
    """Nodes/edges of one ring for visualisation."""
    for comp in nx.connected_components(_graph(df)):
        if sum(n.startswith("c:") for n in comp) < min_accounts or ring_id_for(comp) != ring_id:
            continue
        ids = {n[2:] for n in comp if n.startswith("c:")}
        g = df[df["customer_id"].isin(ids)]
        nodes = []
        for n in sorted(comp):
            kind, raw = n[0], n[2:]
            col = {"c": "customer_id", "d": "device_id", "p": "payment_id"}[kind]
            rows = g[g[col] == raw]
            nodes.append({"id": n, "type": {"c": "customer", "d": "device", "p": "card"}[kind], "label": raw,
                          "risk": float(rows["risk_score"].max()) if len(rows) else 0.0, "transactions": int(len(rows))})
        edges = [{"source": f"c:{cu}", "target": f"{k}:{x}", "weight": int(n)}
                 for k, col in (("d", "device_id"), ("p", "payment_id"))
                 for (cu, x), n in g.groupby(["customer_id", col]).size().items()]
        return {"ring_id": ring_id, "nodes": nodes, "edges": edges}
    return None
