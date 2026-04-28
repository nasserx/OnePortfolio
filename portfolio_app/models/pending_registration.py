"""PendingRegistration model — staged sign-ups awaiting email verification.

A row exists here for every sign-up attempt where the user has not yet
confirmed the 6-digit OTP delivered to their email. Once the OTP is
verified, the row is promoted into the ``user`` table and deleted.

Holding pending sign-ups in a separate table — instead of inserting into
``user`` with ``is_verified=False`` — keeps the live users table free of
unverified noise and prevents the username/email from being squatted by
an abandoned attempt longer than ``expires_at``.
"""

from datetime import datetime, timezone
from portfolio_app import db


class PendingRegistration(db.Model):
    """A staged sign-up awaiting email-OTP confirmation."""

    __tablename__ = 'pending_registration'

    id = db.Column(db.Integer, primary_key=True)
    # Long random token primarily used for invalidation lookups. Each
    # row also carries the 6-digit OTP the user sees in their inbox.
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    verification_code = db.Column(db.String(6), nullable=False)
    verification_code_expires_at = db.Column(db.DateTime, nullable=False)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    # Hard 24-hour TTL for the staged record itself, separate from the
    # short-lived OTP — even if the user keeps requesting fresh codes, we
    # don't want a pending row to live forever.
    expires_at = db.Column(db.DateTime, nullable=False)

    def __repr__(self) -> str:
        return f'<PendingRegistration {self.email}>'
