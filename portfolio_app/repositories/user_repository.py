"""User repository for database operations on User model."""

from datetime import datetime
from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository for User model database operations."""

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username (case-sensitive).

        Args:
            username: The username to search for

        Returns:
            The user if found, None otherwise
        """
        return self.model.query.filter_by(username=username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address (case-insensitive).

        Args:
            email: The email address to search for

        Returns:
            The user if found, None otherwise
        """
        return self.model.query.filter(
            self.model.email == email.lower()
        ).first()

    def get_by_username_or_email(self, identifier: str) -> Optional[User]:
        """Get user by username or email address.

        Args:
            identifier: A username or email address.

        Returns:
            The user if found, None otherwise.
        """
        return self.model.query.filter(
            (self.model.username == identifier) |
            (self.model.email == identifier.lower())
        ).first()

    def get_by_pending_email(self, email: str) -> Optional[User]:
        """Get a verified user who has a pending email change to this address.

        Args:
            email: The pending (unconfirmed) new email address.

        Returns:
            The user if found, None otherwise.
        """
        return self.model.query.filter(
            self.model.pending_email == email.lower()
        ).first()

    def get_expired_unverified(self, now: datetime) -> List[User]:
        """Return unverified accounts whose verification code has expired.

        Args:
            now: Current UTC datetime to compare against expiry.

        Returns:
            List of expired unverified User objects.
        """
        return self.model.query.filter(
            self.model.is_verified == False,
            self.model.verification_code_expires_at != None,
            self.model.verification_code_expires_at < now,
        ).all()

    def count(self) -> int:
        """Return total number of registered users."""
        return self.model.query.count()
