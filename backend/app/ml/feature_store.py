"""
Incremental per-entity feature store, used for BOTH batch training and live scoring
(train/serve consistency).

LEAKAGE RULES (spec section 23)
  1. Features for transaction T only use information available at T.
  2. State is updated AFTER features are computed.
  3. Outcomes (fraud confirmation, chargeback, return) are NOT visible immediately. They enter the
     history `label_delay_days` after the transaction, like real chargebacks. Replaying history
     therefore never lets a label influence the features of nearby transactions.
  4. Graph features come from a union-find over customer/device/card links seen so far.
"""
from collections import defaultdict, deque
from datetime import timedelta

from app.core.config import LABEL_DELAY_DAYS

FEATURE_COLUMNS = [
    "amount", "amount_dev_from_avg",
    "tx_count_last_10min_cust", "tx_count_last_1h_cust", "tx_count_last_24h_cust", "amount_last_24h_cust",
    "customer_account_age_days", "customer_tx_count_30d", "customer_avg_amount_prior",
    "customer_historical_fraud_rate", "customer_historical_chargebacks", "customer_return_rate_prior",
    "device_accounts_24h", "device_cards_24h", "device_tx_count_10min", "device_tx_count_1h",
    "device_tx_count_30d", "device_historical_fraud_rate",
    "payment_accounts_count", "payment_tx_count_30d", "payment_historical_chargeback_rate",
    "is_new_region_for_customer", "category_new_for_customer", "hour_of_day",
    "graph_component_accounts", "graph_component_devices", "graph_component_payments",
]


class FeatureStore:
    def __init__(self, label_delay_days: float = LABEL_DELAY_DAYS):
        self.delay = timedelta(days=label_delay_days)
        self.pending = deque()  # (release_ts, customer, device, payment, fraud, return, chargeback)
        self.cust = defaultdict(lambda: {"amt_sum": 0.0, "n": 0, "labeled": 0, "fraud": 0,
                                          "chargebacks": 0, "returns": 0, "cats": set()})
        self.dev = defaultdict(lambda: {"n": 0, "labeled": 0, "fraud": 0})
        self.pay = defaultdict(lambda: {"accounts": set(), "n": 0, "labeled": 0, "chargebacks": 0})
        self.cust_tx = defaultdict(deque)        # (ts, amount)
        self.dev_tx = defaultdict(deque)         # ts
        self.dev_acc = defaultdict(deque)        # (ts, customer)
        self.dev_card = defaultdict(deque)       # (ts, payment)
        self.win30 = {k: defaultdict(deque) for k in ("c", "d", "p")}  # 30-day tx timestamps (stationary alternative to all-time counters)
        self.home_region = {}
        self.last_ts = None
        self._parent, self._counts = {}, {}      # union-find + per-root [customers, devices, payments]

    # ---- union-find -----------------------------------------------------------
    def _find(self, x):
        if x not in self._parent:
            self._parent[x] = x
            self._counts[x] = [int(x[0] == "c"), int(x[0] == "d"), int(x[0] == "p")]
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def _union(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return ra
        if sum(self._counts[ra]) < sum(self._counts[rb]):
            ra, rb = rb, ra
        self._parent[rb] = ra
        for i in range(3):
            self._counts[ra][i] += self._counts[rb][i]
        del self._counts[rb]
        return ra

    # ---- delayed outcomes -------------------------------------------------------
    def apply_label(self, customer_id, device_id, payment_id, is_fraud=0, is_return=0, is_chargeback=0):
        """Fold a confirmed outcome into history. Called after the delay (replay) or when an analyst
        confirms a case (live)."""
        c, d, p = self.cust[customer_id], self.dev[device_id], self.pay[payment_id]
        c["labeled"] += 1; c["fraud"] += int(is_fraud); c["chargebacks"] += int(is_chargeback); c["returns"] += int(is_return)
        d["labeled"] += 1; d["fraud"] += int(is_fraud)
        p["labeled"] += 1; p["chargebacks"] += int(is_chargeback)

    def _release(self, ts):
        while self.pending and self.pending[0][0] <= ts:
            _, cu, de, pa, f, r, cb = self.pending.popleft()
            self.apply_label(cu, de, pa, f, r, cb)

    # ---- main entry ---------------------------------------------------------------
    def compute_and_update(self, ts, customer_id, device_id, payment_id, amount, account_age_days, ip_region,
                           merchant_category=None, payment_method=None, outcome=None) -> dict:
        """Compute features from state accumulated so far, then update state.
        `outcome` = (is_fraud, is_return, is_chargeback) when replaying history; it is queued and only
        becomes visible after the label delay. Live scoring passes None."""
        self._release(ts)
        f = {}
        c, d, p = self.cust[customer_id], self.dev[device_id], self.pay[payment_id]

        def n30(kind, key):
            w = self.win30[kind][key]
            while w and (ts - w[0]).total_seconds() > 30 * 86400:
                w.popleft()
            return len(w)

        f["customer_tx_count_30d"] = n30("c", customer_id)
        f["customer_avg_amount_prior"] = c["amt_sum"] / c["n"] if c["n"] else amount
        f["amount_dev_from_avg"] = amount / f["customer_avg_amount_prior"] if f["customer_avg_amount_prior"] > 0 else 1.0
        lab = max(c["labeled"], 1)
        f["customer_historical_fraud_rate"] = c["fraud"] / lab if c["labeled"] else 0.0
        f["customer_historical_chargebacks"] = c["chargebacks"]
        f["customer_return_rate_prior"] = c["returns"] / lab if c["labeled"] else 0.0
        f["customer_account_age_days"] = account_age_days

        self.home_region.setdefault(customer_id, ip_region)
        f["is_new_region_for_customer"] = int(ip_region != self.home_region[customer_id])
        f["category_new_for_customer"] = int(bool(merchant_category) and c["n"] > 0 and merchant_category not in c["cats"])

        dq = self.cust_tx[customer_id]
        while dq and (ts - dq[0][0]).total_seconds() > 86400:
            dq.popleft()
        f["tx_count_last_10min_cust"] = sum(1 for t, _ in dq if (ts - t).total_seconds() <= 600)
        f["tx_count_last_1h_cust"] = sum(1 for t, _ in dq if (ts - t).total_seconds() <= 3600)
        f["tx_count_last_24h_cust"] = len(dq)
        f["amount_last_24h_cust"] = sum(a for _, a in dq)

        f["device_tx_count_30d"] = n30("d", device_id)
        f["device_historical_fraud_rate"] = d["fraud"] / d["labeled"] if d["labeled"] else 0.0
        da = self.dev_acc[device_id]
        while da and (ts - da[0][0]).total_seconds() > 86400:
            da.popleft()
        f["device_accounts_24h"] = len({cu for _, cu in da})
        dc = self.dev_card[device_id]
        while dc and (ts - dc[0][0]).total_seconds() > 86400:
            dc.popleft()
        f["device_cards_24h"] = len({pa for _, pa in dc})
        dt = self.dev_tx[device_id]
        while dt and (ts - dt[0]).total_seconds() > 3600:
            dt.popleft()
        f["device_tx_count_10min"] = sum(1 for t in dt if (ts - t).total_seconds() <= 600)
        f["device_tx_count_1h"] = len(dt)

        f["payment_tx_count_30d"] = n30("p", payment_id)
        f["payment_accounts_count"] = len(p["accounts"])
        f["payment_historical_chargeback_rate"] = p["chargebacks"] / p["labeled"] if p["labeled"] else 0.0
        f["hour_of_day"] = ts.hour
        f["amount"] = amount

        # graph: links known at this moment (the request itself carries customer/device/card)
        cn, dn, pn = f"c:{customer_id}", f"d:{device_id}", f"p:{payment_id}"
        self._union(cn, dn)
        root = self._union(cn, pn)
        f["graph_component_accounts"], f["graph_component_devices"], f["graph_component_payments"] = self._counts[root]

        # ---- update state AFTER features ----
        c["amt_sum"] += amount; c["n"] += 1
        if merchant_category:
            c["cats"].add(merchant_category)
        d["n"] += 1; p["n"] += 1; p["accounts"].add(customer_id)
        self.cust_tx[customer_id].append((ts, amount))
        self.win30["c"][customer_id].append(ts); self.win30["d"][device_id].append(ts); self.win30["p"][payment_id].append(ts)
        self.dev_tx[device_id].append(ts)
        self.dev_acc[device_id].append((ts, customer_id))
        self.dev_card[device_id].append((ts, payment_id))
        if outcome is not None:
            self.pending.append((ts + self.delay, customer_id, device_id, payment_id, *[int(x) for x in outcome]))
        self.last_ts = ts if self.last_ts is None or ts > self.last_ts else self.last_ts
        return {k: f[k] for k in FEATURE_COLUMNS}
