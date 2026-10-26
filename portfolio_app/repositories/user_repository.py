"""User repository for database operations on User model."""

from typing import Optional
from contextlib import contextmanager

from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository for User model database operations."""

    @contextmanager
    def email_reservation(self):
        """Serialize cross-table email claims on the supported SQLite backend.

        Services commit their complete workflow. Errors and early returns release
        the reservation with rollback; unrelated pending work is never discarded.
        """
        session = self.db.session()
        if session.new or session.dirty or session.deleted:
            raise RuntimeError('Email reservations require a clean session boundary.')
        connection = session.connection()
        if connection.dialect.name != 'sqlite':
            raise RuntimeError('Email reservation locking requires SQLite.')
        if connection.connection.driver_connection.in_transaction:
            raise RuntimeError('Email reservation must precede database writes.')
        try:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            # Callers may have loaded current_user before waiting for the lock.
            session.expire_all()
            yield
        finally:
            if session.in_transaction():
                session.rollback()

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

    def get_live_pending_email(self, email, now, max_attempts, exclude_user_id=None):
        """Ignore expired/incomplete/exhausted claims, including legacy overlaps."""
        query = self.model.query.filter(
            self.model.pending_email == email.lower(),
            self.model.verification_code.isnot(None),
            self.model.verification_code != '',
            self.model.verification_code_expires_at >= now,
            self.model.verification_code_failed_attempts < max_attempts,
        )
        if exclude_user_id is not None:
            query = query.filter(self.model.id != exclude_user_id)
        return query.first()
