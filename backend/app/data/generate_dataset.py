"""
Synthetic transaction dataset generator for AI Risk Manager.

DATA HONESTY: public fraud datasets lack device/account/network fields, so this data is
SIMULATED and every metric computed on it is relative to simulated ground truth.

Version 2 makes the problem deliberately harder so results are believable:
  * Legit households share devices/cards (so "shared device" alone is not proof of fraud).
  * Six fraud patterns, several of them subtle:
      point_anomaly        one-off stolen-card purchase
      coordinated_ring     many new accounts on ONE device, fast burst
      multi_device_ring    accounts rotate across several devices and a pool of cards
      slow_ring            one device, accounts created over days, normal-looking amounts
      account_takeover     real customer, attacker on a new device/region, moderate amounts
      return_abuse         customers who return most of what they buy
      card_testing         new account probes a card with rapid small purchases, then one large one
  * Label noise: some fraud is never labelled; a few legit rows are mislabelled.
  * Outcome columns (is_return, is_chargeback) that arrive late in production.
"""
import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.core.config import RAW_PATH

REGIONS = ["Chennai", "Mumbai", "Bengaluru", "Hyderabad", "Delhi", "Pune", "Kolkata", "Vijayawada"]
CATEGORIES = ["Electronics", "Fashion", "Groceries", "Travel", "Home", "Beauty", "Sports", "Digital Goods"]
PAYMENT_METHODS = ["Card", "UPI", "Wallet", "NetBanking"]


def generate_dataset(n_customers=6000, n_days=90, avg_tx_per_customer=12, fraud_ring_count=30,
                     card_testing_count=25, multi_device_ring_count=10, slow_ring_count=8, takeover_rate=0.006,
                     return_abuser_rate=0.012, point_fraud_rate=0.005, household_rate=0.05,
                     missed_fraud_label_rate=0.03, false_fraud_label_rate=0.001, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2026, 5, 1)
    end = start + timedelta(days=n_days)
    rows, counter = [], [0]

    def add(**kw):
        kw["transaction_id"] = f"TX{counter[0]:07d}"
        counter[0] += 1
        rows.append(kw)

    # ---- customer population -------------------------------------------------
    customers = []
    for i in range(n_customers):
        customers.append({
            "customer_id": f"C{100000 + i}", "device_id": f"DEV{200000 + i}", "payment_id": f"PAY{300000 + i}",
            "home_region": str(rng.choice(REGIONS)),
            "avg_amount": float(rng.lognormal(7.2, 0.6)),
            "created": start - timedelta(days=int(rng.integers(1, 900))),
            "category": str(rng.choice(CATEGORIES)),
            "abuser": False,
        })
    # households: 2-4 customers genuinely share a device and a card
    k = int(n_customers * household_rate)
    chosen = list(rng.choice(n_customers, size=k, replace=False))
    while len(chosen) >= 2:
        size = min(int(rng.integers(2, 5)), len(chosen))
        grp, chosen = chosen[:size], chosen[size:]
        for j in grp[1:]:
            customers[j]["device_id"] = customers[grp[0]]["device_id"]
            customers[j]["payment_id"] = customers[grp[0]]["payment_id"]
            customers[j]["home_region"] = customers[grp[0]]["home_region"]
    for j in rng.choice(n_customers, size=int(n_customers * return_abuser_rate), replace=False):
        customers[j]["abuser"] = True

    # ---- legitimate behaviour (+ return abusers) -------------------------------
    for c in customers:
        earliest = max(start, c["created"])
        for _ in range(max(1, int(rng.poisson(avg_tx_per_customer)))):
            ts = earliest + timedelta(days=float(rng.uniform(0, max((end - earliest).days, 1))),
                                      hours=float(rng.uniform(0, 24)))
            if ts > end:
                continue
            amount = max(49.0, float(rng.lognormal(np.log(c["avg_amount"]), 0.35)))
            returned = rng.random() < (0.65 if c["abuser"] else 0.07)
            abusive = c["abuser"] and returned
            if c["abuser"]:
                amount *= float(rng.uniform(1.0, 1.8))
            add(customer_id=c["customer_id"], timestamp=ts, amount=round(amount, 2),
                payment_method=str(rng.choice(PAYMENT_METHODS, p=[0.45, 0.35, 0.15, 0.05])),
                device_id=c["device_id"], payment_id=c["payment_id"],
                ip_region=c["home_region"] if rng.random() > 0.03 else str(rng.choice(REGIONS)),
                merchant_category=c["category"] if rng.random() > 0.3 else str(rng.choice(CATEGORIES)),
                account_age_days=max(0, (ts - c["created"]).days),
                is_fraud=int(abusive), fraud_pattern="return_abuse" if abusive else "none",
                is_return=int(returned), is_chargeback=int(rng.random() < 0.001))

    # ---- point anomalies: modify existing legit rows ----------------------------
    legit_idx = [i for i, r in enumerate(rows) if r["fraud_pattern"] == "none"]
    for idx in rng.choice(legit_idx, size=int(len(legit_idx) * point_fraud_rate), replace=False):
        r = rows[idx]
        r["amount"] = round(r["amount"] * float(rng.uniform(2.5, 7)), 2)
        if rng.random() < 0.7:
            r["ip_region"] = str(rng.choice(REGIONS))
        if rng.random() < 0.6:
            r["merchant_category"] = str(rng.choice(["Electronics", "Digital Goods", "Travel"]))
        r.update(is_fraud=1, fraud_pattern="point_anomaly", is_chargeback=int(rng.random() < 0.75))

    # ---- account takeover: real victim, attacker on a new device ---------------
    victims = rng.choice(n_customers, size=int(n_customers * takeover_rate), replace=False)
    for n, vi in enumerate(victims):
        v = customers[vi]
        t0 = start + timedelta(days=float(rng.uniform(20, n_days - 1)))
        for _ in range(int(rng.integers(2, 6))):
            ts = t0 + timedelta(minutes=float(rng.uniform(0, 150)))
            if ts > end:
                continue
            add(customer_id=v["customer_id"], timestamp=ts,
                amount=round(v["avg_amount"] * float(rng.uniform(1.5, 4.0)), 2), payment_method="Card",
                device_id=f"DEVATO{n:05d}", payment_id=v["payment_id"],
                ip_region=str(rng.choice([r for r in REGIONS if r != v["home_region"]])),
                merchant_category=str(rng.choice(CATEGORIES)), account_age_days=max(0, (ts - v["created"]).days),
                is_fraud=1, fraud_pattern="account_takeover", is_return=0, is_chargeback=int(rng.random() < 0.8))

    def ring_tx(cust, ts, amt, dev, pay, age, pattern):
        add(customer_id=cust, timestamp=ts, amount=round(amt, 2), payment_method="Card", device_id=dev,
            payment_id=pay, ip_region=str(rng.choice(REGIONS)),
            merchant_category=str(rng.choice(["Digital Goods", "Electronics"] if rng.random() < 0.6 else CATEGORIES)),
            account_age_days=age, is_fraud=1, fraud_pattern=pattern, is_return=0,
            is_chargeback=int(rng.random() < 0.75))

    # ---- coordinated ring: one device, fast burst ------------------------------
    for r in range(fraud_ring_count):
        t0 = start + timedelta(days=float(rng.uniform(0, n_days - 2)))
        base = float(rng.uniform(2000, 9000))
        for a in range(int(rng.integers(3, 13))):
            for _ in range(int(rng.integers(1, 5))):
                ts = t0 + timedelta(minutes=float(rng.uniform(0, 120)))
                if ts <= end:
                    ring_tx(f"CR{r:04d}{a:02d}", ts, base * float(rng.uniform(0.6, 1.4)), f"DEVRING{r:04d}",
                            f"PAYR{r:04d}{a:02d}", int(rng.integers(0, 8)), "coordinated_ring")

    # ---- multi-device ring: device + card rotation -----------------------------
    for r in range(multi_device_ring_count):
        t0 = start + timedelta(days=float(rng.uniform(0, n_days - 3)))
        devices = [f"DEVMD{r:03d}{d}" for d in range(int(rng.integers(4, 9)))]
        cards = [f"PAYMD{r:03d}{p}" for p in range(int(rng.integers(3, 6)))]
        base = float(rng.uniform(1500, 6000))
        for a in range(int(rng.integers(6, 16))):
            for _ in range(int(rng.integers(1, 4))):
                ts = t0 + timedelta(hours=float(rng.uniform(0, 8)))
                if ts <= end:
                    ring_tx(f"CM{r:03d}{a:02d}", ts, base * float(rng.uniform(0.7, 1.3)), str(rng.choice(devices)),
                            str(rng.choice(cards)), int(rng.integers(0, 5)), "multi_device_ring")

    # ---- slow ring: same device, accounts trickle in over days, normal amounts --
    for r in range(slow_ring_count):
        t0 = start + timedelta(days=float(rng.uniform(0, n_days - 14)))
        for a in range(int(rng.integers(5, 12))):
            joined = t0 + timedelta(days=float(rng.uniform(0, 10)))
            for _ in range(int(rng.integers(1, 3))):
                ts = joined + timedelta(hours=float(rng.uniform(0, 72)))
                if ts <= end:
                    ring_tx(f"CS{r:03d}{a:02d}", ts, float(rng.uniform(900, 3000)), f"DEVSLOW{r:03d}",
                            f"PAYS{r:03d}{a:02d}", int(rng.integers(0, 15)), "slow_ring")

    # ---- card testing: rapid small probes then one large purchase ----------------
    for r in range(card_testing_count):
        t0 = start + timedelta(days=float(rng.uniform(0, n_days - 1)))
        for a in range(int(rng.integers(1, 4))):
            k = int(rng.integers(5, 11))
            times = sorted(t0 + timedelta(minutes=float(rng.uniform(0, 25))) for _ in range(k))
            for j, ts in enumerate(times):
                if ts <= end:
                    amt = float(rng.uniform(60, 350)) if j < k - 1 else float(rng.uniform(3000, 8000))
                    ring_tx(f"CT{r:03d}{a:02d}", ts, amt, f"DEVCT{r:03d}{a}", f"PAYCT{r:03d}{a}", int(rng.integers(0, 6)), "card_testing")

    df = pd.DataFrame(rows)

    # ---- label noise: undetected fraud + a few mislabelled legit rows -----------
    fraud_mask = df["is_fraud"] == 1
    df.loc[fraud_mask & (rng.random(len(df)) < missed_fraud_label_rate), "is_fraud"] = 0
    df.loc[~fraud_mask & (rng.random(len(df)) < false_fraud_label_rate), "is_fraud"] = 1
    return df.sort_values("timestamp").reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", type=int, default=6000)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    data = generate_dataset(n_customers=a.customers, n_days=a.days, seed=a.seed)
    data.to_csv(RAW_PATH, index=False)
    print(f"Generated {len(data):,} transactions ({data['is_fraud'].mean()*100:.2f}% labelled fraud) -> {RAW_PATH}")
    print(data["fraud_pattern"].value_counts().to_string())
