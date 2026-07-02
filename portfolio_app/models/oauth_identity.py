"""External OAuth identity linked to a local user."""

from datetime import datetime, timezone
from sqlalchemy.orm import validates
from portfolio_app import db


class OAuthIdentity(db.Model):
    """Persistent link between a provider subject and a local user."""

    __tablename__ = 'oauth_identity'
    __table_args__ = (
        db.UniqueConstraint(
            'provider', 'provider_subject',
            name='uq_oauth_identity_provider_subject',
        ),
        db.UniqueConstraint(
            'user_id', 'provider',
            name='uq_oauth_identity_user_provider',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(50), nullable=False)
    provider_subject = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @validates('provider')
    def _normalize_provider(self, _key, provider: str) -> str:
        """Store provider identifiers in one canonical form."""
        if not isinstance(provider, str):
            raise ValueError('OAuth provider must be a string.')
        normalized = provider.strip().lower()
        if not normalized:
            raise ValueError('OAuth provider is required.')
        return normalized

    def __repr__(self) -> str:
        return (
            f'<OAuthIdentity id={self.id} '
            f'provider={self.provider} user_id={self.user_id}>'
        )
