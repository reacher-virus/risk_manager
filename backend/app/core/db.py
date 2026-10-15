"""Persistence (SQLAlchemy). SQLite by default; set DATABASE_URL to a postgresql+psycopg2:// URL for PostgreSQL."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import COST_FN, COST_FP, DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True,
                       connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ScoredTransaction(Base):
    __tablename__ = "scored_transactions"
    transaction_id = Column(String(64), primary_key=True)
    customer_id = Column(String(64), index=True)
    device_id = Column(String(64), index=True)
    payment_id = Column(String(64), index=True)
    amount = Column(Float)
    ip_region = Column(String(64))
    merchant_category = Column(String(64))
    payment_method = Column(String(32))
    account_age_days = Column(Float)
    ts = Column(DateTime, index=True)
    risk_score = Column(Float, index=True)
    anomaly_score = Column(Float)
    risk_level = Column(String(16))
    decision = Column(String(32))
    reasons = Column(JSON)
    features = Column(JSON)
    source = Column(String(16), default="api")
    created_at = Column(DateTime, default=utcnow)


class Review(Base):
    """Analyst action (APPROVE/HOLD/ESCALATE) and/or feedback label (FRAUD/LEGIT) on a transaction."""
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), index=True)
    action = Column(String(16), nullable=True)
    label = Column(String(16), nullable=True)
    note = Column(Text, nullable=True)
    actor = Column(String(64))
    created_at = Column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=utcnow, index=True)
    actor = Column(String(64))
    action = Column(String(48), index=True)
    transaction_id = Column(String(64), nullable=True)
    detail = Column(JSON, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(String(256))


def init_db():
    """Create tables. Safe when several workers/processes start at once on a fresh database: the loser of the
    create-table race just retries (create_all skips tables that now exist)."""
    import time
    from sqlalchemy.exc import OperationalError, ProgrammingError
    from app.auth import models  # noqa: F401  (registers the auth tables on Base)
    for attempt in range(5):
        try:
            Base.metadata.create_all(engine)
            return
        except (OperationalError, ProgrammingError):
            if attempt == 4:
                raise
            time.sleep(0.3 * (attempt + 1))


@contextmanager
def session_scope():
    s = Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def audit(actor: str, action: str, transaction_id: str | None = None, detail: dict | None = None, session=None):
    """Pass `session` when already inside a transaction: a second writer connection would deadlock on SQLite."""
    row = AuditLog(actor=actor, action=action, transaction_id=transaction_id, detail=detail)
    if session is not None:
        session.add(row)
        return
    with session_scope() as s:
        s.add(row)


# ---- settings ---------------------------------------------------------------------
def get_setting(key: str, default=None):
    with session_scope() as s:
        row = s.get(Setting, key)
        return row.value if row else default


def set_setting(key: str, value) -> None:
    with session_scope() as s:
        s.merge(Setting(key=key, value=str(value)))


def get_costs() -> tuple[float, float]:
    return float(get_setting("cost_fp", COST_FP)), float(get_setting("cost_fn", COST_FN))


# ---- reviews -------------------------------------------------------------------------
def review_state() -> dict:
    """Latest action/label per transaction."""
    out: dict = {}
    with session_scope() as s:
        for r in s.execute(select(Review).order_by(Review.id)).scalars():
            st = out.setdefault(r.transaction_id, {"action": None, "label": None, "note": None, "actor": None, "at": None})
            if r.action:
                st["action"] = r.action
            if r.label:
                st["label"] = r.label
            if r.note:
                st["note"] = r.note
            st["actor"], st["at"] = r.actor, r.created_at.isoformat()
    return out


def review_history(tx_id: str) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(Review).where(Review.transaction_id == tx_id).order_by(Review.id.desc())).scalars().all()
        return [{"action": r.action, "label": r.label, "note": r.note, "actor": r.actor, "at": r.created_at.isoformat()} for r in rows]


def feedback_training_rows() -> pd.DataFrame:
    """Live transactions with an analyst label -> training rows (features + is_fraud)."""
    from app.ml.feature_store import FEATURE_COLUMNS
    labels = {tx: st["label"] for tx, st in review_state().items() if st["label"]}
    rows = []
    with session_scope() as s:
        for t in s.execute(select(ScoredTransaction).where(ScoredTransaction.transaction_id.in_(list(labels) or [""]))).scalars():
            if t.features:
                rows.append({**{k: t.features.get(k, 0) for k in FEATURE_COLUMNS}, "is_fraud": int(labels[t.transaction_id] == "FRAUD")})
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS + ["is_fraud"])


def live_dataframe() -> pd.DataFrame:
    cols = ["transaction_id", "customer_id", "device_id", "payment_id", "amount", "timestamp", "ip_region",
            "merchant_category", "payment_method", "risk_score", "anomaly_score"]
    with session_scope() as s:
        rows = [{"transaction_id": t.transaction_id, "customer_id": t.customer_id, "device_id": t.device_id,
                 "payment_id": t.payment_id, "amount": t.amount, "timestamp": t.ts, "ip_region": t.ip_region,
                 "merchant_category": t.merchant_category, "payment_method": t.payment_method,
                 "risk_score": t.risk_score, "anomaly_score": t.anomaly_score}
                for t in s.execute(select(ScoredTransaction)).scalars()]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["is_fraud"] = float("nan")
    df["source"] = "live"
    return df
