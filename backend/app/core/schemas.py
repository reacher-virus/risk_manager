from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TransactionIn(BaseModel):
    transaction_id: Optional[str] = None
    customer_id: str
    amount: float = Field(gt=0)
    device_id: str
    payment_id: Optional[str] = None
    account_age_days: float = 0
    ip_region: Optional[str] = "Unknown"
    merchant_category: Optional[str] = None
    payment_method: Optional[str] = None
    timestamp: Optional[datetime] = None


class Contribution(BaseModel):
    feature: str
    label: str
    value: float
    contribution: float


class PredictResponse(BaseModel):
    transaction_id: str
    risk_score: float
    risk_level: str
    decision: str
    reasons: list[str]
    contributions: list[Contribution] = []
    anomaly_score: float
    novel_pattern: bool = False


class ReviewIn(BaseModel):
    action: Optional[Literal["APPROVE", "HOLD", "ESCALATE"]] = None
    label: Optional[Literal["FRAUD", "LEGIT"]] = None
    note: Optional[str] = Field(default=None, max_length=1000)


class CostsIn(BaseModel):
    cost_fp: float = Field(gt=0)
    cost_fn: float = Field(gt=0)


class ThresholdIn(BaseModel):
    threshold: Optional[float] = Field(default=None, gt=0, lt=1, description="null resets to the trained value")


class SimulateIn(BaseModel):
    scenario: Literal["normal", "velocity_burst", "fraud_ring", "multi_device_ring", "account_takeover"]
    n: int = Field(default=8, ge=1, le=40)
