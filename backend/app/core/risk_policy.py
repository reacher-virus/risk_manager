"""Score -> severity/decision. Bands are DERIVED from the cost-optimal threshold, not hard-coded (spec section 9).

  LOW       score <  threshold/2      ALLOW
  MEDIUM    threshold/2 <= score < threshold     MONITOR
  HIGH      threshold <= score < hold_at         REVIEW
  CRITICAL  score >= hold_at          HOLD_FOR_VERIFICATION
where hold_at = clamp(threshold + 0.2, 0.5, 0.95): calibrated probabilities of 50%+ mean "more likely fraud than not".
"""
LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DECISIONS = {"LOW": "ALLOW", "MEDIUM": "MONITOR", "HIGH": "REVIEW", "CRITICAL": "HOLD_FOR_VERIFICATION"}


def cutoffs(threshold: float) -> dict:
    return {"MEDIUM": threshold / 2, "HIGH": threshold, "CRITICAL": max(0.5, min(0.95, threshold + 0.2))}


def classify(score: float, threshold: float = 0.3) -> tuple[str, str]:
    c = cutoffs(threshold)
    level = "CRITICAL" if score >= c["CRITICAL"] else "HIGH" if score >= c["HIGH"] else "MEDIUM" if score >= c["MEDIUM"] else "LOW"
    return level, DECISIONS[level]


def min_score_for(level: str, threshold: float) -> float:
    return 0.0 if level.upper() == "LOW" else cutoffs(threshold)[level.upper()]
