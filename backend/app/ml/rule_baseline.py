"""
Layer 1 — Rule-Based Baseline (spec §8).

Simple, explainable rules used purely as a comparison baseline against the
ML model (spec §18 Model Comparison). Thresholds here are illustrative and
tuned loosely against the synthetic training data.
"""

import pandas as pd
import numpy as np


def rule_based_score(df: pd.DataFrame) -> pd.Series:
    """
    Returns a score in [0,1] (fraction of triggered rules) and could be
    thresholded at 0.34 (>=1 of 3 rules) or similar. We keep it simple:
    each rule contributes a fixed weight if triggered, capped at 1.0.
    """
    score = pd.Series(0.0, index=df.index)

    # Rule 1: velocity burst
    score += 0.4 * (df["tx_count_last_10min_cust"] > 3)

    # Rule 2: device shared by many accounts in 24h
    score += 0.45 * (df["device_accounts_24h"] >= 3)

    # Rule 3: amount far above customer's own historical average
    score += 0.35 * (df["amount_dev_from_avg"] > 5)

    # Rule 4: brand-new account transacting large amount
    score += 0.25 * ((df["customer_account_age_days"] <= 2) & (df["amount"] > 1500))

    # Rule 5: customer who returns most of what they buy
    score += 0.4 * (df["customer_return_rate_prior"] > 0.35)

    return score.clip(0, 1)


def rule_based_predict(df: pd.DataFrame, threshold: float = 0.4) -> pd.Series:
    return (rule_based_score(df) >= threshold).astype(int)
