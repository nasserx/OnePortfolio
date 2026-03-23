"""User repository for database operations on User model."""

from typing import Optional
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

    def count(self) -> int:
        """Return total number of registered users."""
        return self.model.query.count()
