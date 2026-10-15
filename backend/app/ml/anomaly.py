"""Unsupervised anomaly layer (Isolation Forest). Catches patterns the supervised model never saw labels for."""
import numpy as np
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    def __init__(self, seed: int = 42):
        self.model = IsolationForest(n_estimators=200, random_state=seed, n_jobs=-1)
        self.ref = None

    def fit(self, X):
        self.model.fit(X)
        self.ref = np.sort(-self.model.score_samples(X))
        return self

    def score(self, X) -> np.ndarray:
        """0..1 percentile of how unusual each row is relative to the training population."""
        raw = -self.model.score_samples(X)
        return np.searchsorted(self.ref, raw, side="right") / len(self.ref)
