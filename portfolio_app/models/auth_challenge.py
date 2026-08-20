"""Persisted, single-use authentication OTP challenges."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint

from portfolio_app import db


class AuthChallenge(db.Model):
    """One active email challenge for login, registration, or recent auth."""

    __tablename__ = 'auth_challenge'
    __table_args__ = (
        CheckConstraint(
            '(user_id IS NOT NULL AND pending_registration_id IS NULL) OR '
            '(user_id IS NULL AND pending_registration_id IS NOT NULL)',
            name='ck_auth_challenge_exactly_one_target',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(32), nullable=False)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    pending_registration_id = db.Column(
        db.Integer,
        db.ForeignKey('pending_registration.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    code_digest = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship(
        'User',
        foreign_keys=[user_id],
        back_populates='auth_challenges',
    )
    pending_registration = db.relationship(
        'PendingRegistration',
        foreign_keys=[pending_registration_id],
        back_populates='auth_challenges',
    )

    def __repr__(self) -> str:
        return f'<AuthChallenge id={self.id} purpose={self.purpose}>'
