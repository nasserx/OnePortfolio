"""User repository for database operations on User model."""

from typing import Optional
from sqlalchemy import update

from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository for User model database operations."""

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username (case-sensitive)."""
        return self.model.query.filter_by(username=username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address (case-insensitive)."""
        return self.model.query.filter(
            self.model.email == email.lower()
        ).first()

    def get_by_username_or_email(self, identifier: str) -> Optional[User]:
        """Get user by username or email address."""
        return self.model.query.filter(
            (self.model.username == identifier) |
            (self.model.email == identifier.lower())
        ).first()

    def get_by_pending_email(self, email: str) -> Optional[User]:
        """Get a verified user who has a pending email change to this address."""
        return self.model.query.filter(
            self.model.pending_email == email.lower()
        ).first()

    def consume_password_reset(
        self,
        email: str,
        expected_jti: str,
        password_hash: str,
    ) -> bool:
        """Atomically apply a password reset while consuming its live JTI.

        The expected JTI is part of the database UPDATE predicate. Exactly
        one affected row means the reset state was still live and has now
        been consumed; any other result is rolled back and treated as a
        failed reset.
        """
        result = self.db.session.execute(
            update(self.model)
            .where(
                self.model.email == email.lower(),
                self.model.password_reset_jti == expected_jti,
            )
            .values(
                password_hash=password_hash,
                password_reset_jti=None,
                auth_generation=self.model.auth_generation + 1,
                failed_login_attempts=0,
                locked_until=None,
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount != 1:
            self.db.session.rollback()
            return False

        self.db.session.commit()
        return True
