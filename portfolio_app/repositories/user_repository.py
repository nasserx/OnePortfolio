"""User repository for database operations on User model."""

from typing import Optional

from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository for User model database operations."""

    def delete(self, user):
        """Confirmed whole-account removal resolves only wholly owned transfers.

        This and the existing user/portfolio cascades commit in one transaction.
        Individual portfolio deletion does NOT use this path. Malformed cross-owner
        links are deliberately left restricted instead of changing another user.
        """
        from portfolio_app.models import Portfolio, PortfolioTransfer
        owned = self.db.session.query(Portfolio.id).filter(Portfolio.user_id == user.id)
        PortfolioTransfer.query.filter(
            PortfolioTransfer.source_portfolio_id.in_(owned),
            PortfolioTransfer.destination_portfolio_id.in_(owned),
        ).delete(synchronize_session='fetch')
        super().delete(user)

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username (case-sensitive)."""
        return self.model.query.filter_by(username=username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address (case-insensitive)."""
        return self.model.query.filter(
            self.model.email == email.lower()
        ).first()

    def get_by_pending_email(self, email: str) -> Optional[User]:
        """Get a verified user who has a pending email change to this address."""
        return self.model.query.filter(
            self.model.pending_email == email.lower()
        ).first()
