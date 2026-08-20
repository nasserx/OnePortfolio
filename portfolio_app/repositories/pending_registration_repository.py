"""Repository for PendingRegistration model."""

from datetime import datetime
from typing import Optional

from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.repositories.base import BaseRepository


class PendingRegistrationRepository(BaseRepository[PendingRegistration]):
    """Repository for staged sign-ups awaiting OTP verification."""

    def get_by_email(self, email: str) -> Optional[PendingRegistration]:
        return self.model.query.filter(self.model.email == email.lower()).first()

    def get_by_username(self, username: str) -> Optional[PendingRegistration]:
        return self.model.query.filter_by(username=username).first()

    def purge_expired(self, now: datetime) -> int:
        """Remove rows whose 24-hour TTL has passed. Returns the count purged."""
        rows = self.model.query.filter(self.model.expires_at < now).all()
        for row in rows:
            self.db.session.delete(row)
        return len(rows)
