"""Cached ring detection over held-out + live data."""
from app.api.state import S
import networkx as nx

from app.ml.graph import _graph, detect_rings, ring_graph, ring_id_for

_cache: dict = {}


def get_rings(min_accounts: int = 3) -> list[dict]:
    df = S.combined_df()
    key = (len(df), id(df), min_accounts)
    if key not in _cache:
        _cache.clear()
        _cache[key] = detect_rings(df, min_accounts)
    return _cache[key]


def get_ring_graph(ring_id: str, min_accounts: int = 3):
    return ring_graph(S.combined_df(), ring_id, min_accounts)


def ring_of_customer(customer_id: str, min_accounts: int = 3) -> str | None:
    df = S.combined_df()
    # cheap path: only build the graph around this customer's neighbourhood
    sub = df[df["customer_id"] == customer_id]
    if sub.empty:
        return None
    devs, pays = set(sub["device_id"]), set(sub["payment_id"])
    near = df[df["device_id"].isin(devs) | df["payment_id"].isin(pays)]
    # expand two hops so full networks resolve
    for _ in range(2):
        custs = set(near["customer_id"])
        near = df[df["customer_id"].isin(custs)]
        devs, pays = set(near["device_id"]), set(near["payment_id"])
        near = df[df["device_id"].isin(devs) | df["payment_id"].isin(pays) | df["customer_id"].isin(custs)]
    for comp in nx.connected_components(_graph(near)):
        if f"c:{customer_id}" in comp:
            return ring_id_for(comp) if sum(n.startswith("c:") for n in comp) >= min_accounts else None
    return None
