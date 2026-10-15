"""Auth tables. All access goes through the SQLAlchemy ORM (parameterised queries): there is no raw SQL anywhere."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.db import Base, utcnow


def new_id() -> str:
    return uuid.uuid4().hex  # 128 random bits: not guessable, not sequential


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=new_id)
    email = Column(String(254), unique=True, nullable=False, index=True)       # stored lower-cased
    email_verified = Column(Boolean, nullable=False, default=False)
    password_hash = Column(String(255), nullable=False)                          # Argon2id; never the password
    full_name = Column(String(80), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")                  # viewer | analyst | admin
    status = Column(String(16), nullable=False, default="active")                # active | disabled (unverified sign-ups never reach this table)
    token_version = Column(Integer, nullable=False, default=0)                   # bump = every issued token dies instantly
    created_at = Column(DateTime, default=utcnow)
    password_changed_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(64), nullable=True)


class AuthSession(Base):
    """One row per login. The access JWT carries this id (`sid`); revoking the row kills the session at once."""
    __tablename__ = "auth_sessions"
    id = Column(String(32), primary_key=True, default=new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)                                # absolute lifetime
    revoked_at = Column(DateTime, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)


class RefreshToken(Base):
    """Opaque, single-use, rotating. Only the SHA-256 is stored. Reusing a spent token revokes the whole session."""
    __tablename__ = "refresh_tokens"
    token_hash = Column(String(64), primary_key=True)
    session_id = Column(String(32), ForeignKey("auth_sessions.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class MfaChallenge(Base):
    """A pending second step (emailed one-time code). `user_id` is NULL for decoy challenges (anti-enumeration)."""
    __tablename__ = "mfa_challenges"
    id = Column(String(32), primary_key=True, default=new_id)
    user_id = Column(String(32), nullable=True, index=True)
    purpose = Column(String(16), nullable=False)                                 # signup | login | admin_login
    code_hash = Column(String(64), nullable=False)                               # HMAC(secret, id:code): useless if the DB leaks
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    used_at = Column(DateTime, nullable=True)
    ip = Column(String(64), nullable=True)
    payload = Column(Text, nullable=True)                                        # pending sign-up data; the user row is created only after the code is verified


class Captcha(Base):
    __tablename__ = "captchas"
    id = Column(String(32), primary_key=True, default=new_id)
    answer_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    token_hash = Column(String(64), primary_key=True)                            # SHA-256 of a 256-bit random token
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class RateEvent(Base):
    __tablename__ = "rate_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), nullable=False, index=True)
    ts = Column(DateTime, nullable=False, default=utcnow, index=True)
