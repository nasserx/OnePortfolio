"""User identity model for passwordless authentication."""

from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import text
from portfolio_app import db


class User(UserMixin, db.Model):
    """Passwordless account identity with Flask-Login integration."""

    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    # Preserved byte-for-byte for the rollback window. Passwordless runtime
    # never reads it, and newly created accounts leave it null.
    password_hash = db.Column(db.String(255), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    # Keyed HMAC-SHA-256 digest of the delivered six-digit email-change OTP.
    verification_code = db.Column(db.String(64), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)
    # Number of consecutive bad-OTP attempts on the pending-email-update flow.
    # Reset on success or when a new code is generated; the code is wiped
    # after MAX_OTP_ATTEMPTS failures so the user must request a fresh one.
    verification_code_failed_attempts = db.Column(db.Integer, default=0, nullable=False)

    pending_email = db.Column(db.String(120), nullable=True)

    # Keyed HMAC-SHA-256 digest of the delivered six-digit deletion OTP.
    deletion_code = db.Column(db.String(64), nullable=True)
    deletion_code_expires_at = db.Column(db.DateTime, nullable=True)
    # Same lockout idea for the account-deletion OTP.
    deletion_code_failed_attempts = db.Column(db.Integer, default=0, nullable=False)

    # Preserved inert password-login lockout state for the rollback window.
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    # Preserved inert password-reset state for the rollback window.
    password_reset_jti = db.Column(db.String(32), nullable=True)

    # Server-authoritative generation bound into every Flask-Login identity.
    # Incrementing it invalidates older signed identities globally.
    auth_generation = db.Column(
        db.Integer,
        default=0,
        server_default=text('0'),
        nullable=False,
    )

    portfolios = db.relationship(
        'Portfolio',
        backref='owner',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    oauth_identities = db.relationship(
        'OAuthIdentity',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    auth_challenges = db.relationship(
        'AuthChallenge',
        back_populates='user',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )

    def get_id(self) -> str:
        """Return the versioned Flask-Login identity for this credential era."""
        return f'v1:{self.id}:{self.auth_generation}'

    def __repr__(self) -> str:
        return f'<User {self.username}>'
