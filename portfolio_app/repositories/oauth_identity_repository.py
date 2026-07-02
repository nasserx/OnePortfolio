"""Repository for OAuthIdentity model lookups."""

from typing import Optional

from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.repositories.base import BaseRepository


class OAuthIdentityRepository(BaseRepository[OAuthIdentity]):
    """Repository for external OAuth identity links."""

    def get_by_provider_subject(
        self,
        provider: str,
        provider_subject: str,
    ) -> Optional[OAuthIdentity]:
        """Return an identity by provider and opaque provider subject."""
        return self.model.query.filter_by(
            provider=provider.lower(),
            provider_subject=provider_subject,
        ).first()

    def get_for_user_and_provider(
        self,
        user_id: int,
        provider: str,
    ) -> Optional[OAuthIdentity]:
        """Return a user's identity link for a provider."""
        return self.model.query.filter_by(
            user_id=user_id,
            provider=provider.lower(),
        ).first()

    def create(
        self,
        user_id: int,
        provider: str,
        provider_subject: str,
    ) -> OAuthIdentity:
        """Create and add an OAuth identity link without committing."""
        identity = self.model(
            user_id=user_id,
            provider=provider.lower(),
            provider_subject=provider_subject,
        )
        self.add(identity)
        return identity
