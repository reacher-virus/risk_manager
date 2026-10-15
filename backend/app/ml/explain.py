"""
Explainability (spec section 11): real per-prediction attributions.
  * Tree models  -> SHAP TreeExplainer
  * Linear models -> coefficient x standardised value
  * Fallback      -> rule triggers weighted by global importance
Raw attributions are turned into plain-English reasons via DESCRIBE.
"""
from typing import Dict, List

import numpy as np
import pandas as pd

from app.ml.feature_store import FEATURE_COLUMNS

try:
    import shap
except Exception:  # pragma: no cover
    shap = None

LABELS = {
    "amount": "Transaction amount", "amount_dev_from_avg": "Amount vs customer average",
    "tx_count_last_10min_cust": "Customer tx in last 10 min", "tx_count_last_1h_cust": "Customer tx in last hour",
    "tx_count_last_24h_cust": "Customer tx in last 24h", "amount_last_24h_cust": "Customer spend in last 24h",
    "customer_account_age_days": "Account age (days)", "customer_tx_count_30d": "Customer tx in last 30 days",
    "customer_avg_amount_prior": "Customer average amount", "customer_historical_fraud_rate": "Customer confirmed-fraud rate",
    "customer_historical_chargebacks": "Customer chargebacks",
    "customer_return_rate_prior": "Customer return rate", "device_accounts_24h": "Accounts on device (24h)",
    "device_cards_24h": "Cards on device (24h)", "device_tx_count_10min": "Device tx in last 10 min",
    "device_tx_count_1h": "Device tx in last hour", "device_tx_count_30d": "Device tx in last 30 days",
    "device_historical_fraud_rate": "Device confirmed-fraud rate", "payment_accounts_count": "Accounts on payment instrument",
    "payment_tx_count_30d": "Payment instrument tx in 30 days", "payment_historical_chargeback_rate": "Payment chargeback rate",
    "is_new_region_for_customer": "New region for customer", "category_new_for_customer": "New category for customer",
    "hour_of_day": "Hour of day", "graph_component_accounts": "Linked accounts in network",
    "graph_component_devices": "Linked devices in network", "graph_component_payments": "Linked cards in network",
}

DESCRIBE = {
    "amount": lambda v: f"Transaction amount is high (Rs {v:,.0f})",
    "amount_dev_from_avg": lambda v: f"Amount is {v:.1f}x this customer's usual spend",
    "tx_count_last_10min_cust": lambda v: f"{int(v)} earlier transactions from this customer in the last 10 minutes",
    "tx_count_last_1h_cust": lambda v: f"{int(v)} earlier transactions from this customer in the last hour",
    "tx_count_last_24h_cust": lambda v: f"{int(v)} transactions from this customer in 24h",
    "amount_last_24h_cust": lambda v: f"Rs {v:,.0f} already spent by this customer in 24h",
    "customer_account_age_days": lambda v: f"Account is only {int(v)} day(s) old",
    "customer_tx_count_30d": lambda v: f"Customer made {int(v)} transaction(s) in the last 30 days",
    "customer_avg_amount_prior": lambda v: f"Customer's average spend is Rs {v:,.0f}",
    "customer_historical_fraud_rate": lambda v: f"Customer has a {v*100:.0f}% confirmed-fraud rate",
    "customer_historical_chargebacks": lambda v: f"Customer has {int(v)} past chargeback(s)",
    "customer_return_rate_prior": lambda v: f"Customer returns {v*100:.0f}% of orders",
    "device_accounts_24h": lambda v: f"Device used by {int(v)} different accounts in the last 24h",
    "device_cards_24h": lambda v: f"Device used with {int(v)} different cards in 24h",
    "device_tx_count_10min": lambda v: f"{int(v)} earlier transactions from this device in 10 minutes",
    "device_tx_count_1h": lambda v: f"{int(v)} earlier transactions from this device in the last hour",
    "device_tx_count_30d": lambda v: f"Device made {int(v)} transaction(s) in the last 30 days",
    "device_historical_fraud_rate": lambda v: f"Device has a {v*100:.0f}% confirmed-fraud rate",
    "payment_accounts_count": lambda v: f"Card linked to {int(v)} different accounts",
    "payment_tx_count_30d": lambda v: f"Card made {int(v)} transaction(s) in the last 30 days",
    "payment_historical_chargeback_rate": lambda v: f"Card has a {v*100:.0f}% chargeback rate",
    "is_new_region_for_customer": lambda v: "Purchase comes from a region unusual for this customer",
    "category_new_for_customer": lambda v: "Customer never bought from this category before",
    "hour_of_day": lambda v: f"Unusual time of day ({int(v)}:00)",
    "graph_component_accounts": lambda v: f"Connected to a network of {int(v)} accounts via shared devices/cards",
    "graph_component_devices": lambda v: f"Connected to {int(v)} devices in one network",
    "graph_component_payments": lambda v: f"Connected to {int(v)} cards in one network",
}

FALLBACK_TRIGGERS = {
    "device_accounts_24h": lambda v: v >= 3, "device_cards_24h": lambda v: v >= 3, "tx_count_last_10min_cust": lambda v: v >= 2,
    "device_tx_count_10min": lambda v: v >= 3, "amount_dev_from_avg": lambda v: v >= 3, "customer_account_age_days": lambda v: v <= 3,
    "device_historical_fraud_rate": lambda v: v >= 0.1, "payment_historical_chargeback_rate": lambda v: v >= 0.1,
    "is_new_region_for_customer": lambda v: v == 1, "payment_accounts_count": lambda v: v >= 3,
    "graph_component_accounts": lambda v: v >= 3, "customer_return_rate_prior": lambda v: v >= 0.3,
}


class Explainer:
    def __init__(self, base_model, importances: Dict[str, float] | None = None):
        self.model, self.importances = base_model, importances or {}
        self.kind, self.shap = "fallback", None
        if hasattr(base_model, "named_steps"):
            self.kind = "linear"
        elif shap is not None:
            try:
                self.shap, self.kind = shap.TreeExplainer(base_model), "shap"
            except Exception:  # pragma: no cover
                pass

    def contributions(self, X: pd.DataFrame) -> np.ndarray | None:
        """(n_rows, n_features) signed contribution towards fraud risk, or None for the fallback."""
        if self.kind == "shap":
            sv = self.shap.shap_values(X[FEATURE_COLUMNS])
            sv = sv[1] if isinstance(sv, list) else np.asarray(sv)
            return sv[:, :, 1] if sv.ndim == 3 else sv
        if self.kind == "linear":
            scaler, clf = self.model.named_steps["standardscaler"], list(self.model.named_steps.values())[-1]
            return scaler.transform(X[FEATURE_COLUMNS]) * clf.coef_[0]
        return None

    def explain_row(self, feats: dict, contrib_row: np.ndarray | None, top_k: int = 4, n_contrib: int = 8):
        """Returns (reasons, top contributions)."""
        if contrib_row is None:
            hits = [(self.importances.get(k, 0.0), DESCRIBE[k](feats[k])) for k, cond in FALLBACK_TRIGGERS.items()
                    if k in feats and cond(feats[k])]
            hits.sort(reverse=True)
            return ([m for _, m in hits[:top_k]] or ["No individually unusual signals"]), []
        pairs = sorted(zip(FEATURE_COLUMNS, contrib_row), key=lambda kv: kv[1], reverse=True)
        top_pos = pairs[0][1] if pairs else 0
        reasons = [DESCRIBE[k](feats[k]) for k, s in pairs[:top_k] if s > 0 and s >= 0.1 * top_pos and s > 1e-4]
        contribs = [{"feature": k, "label": LABELS[k], "value": float(feats[k]), "contribution": float(s)}
                    for k, s in sorted(pairs, key=lambda kv: abs(kv[1]), reverse=True)[:n_contrib]]
        return (reasons or ["No unusual risk signals"]), contribs
