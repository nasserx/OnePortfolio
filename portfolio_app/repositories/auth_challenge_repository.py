"""Repository for atomic authentication-challenge operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import update

from portfolio_app.models.auth_challenge import AuthChallenge
from portfolio_app.repositories.base import BaseRepository


class AuthChallengeRepository(BaseRepository[AuthChallenge]):
    """Persistence boundary for short-lived, single-use auth challenges."""

    def get_by_token(self, token: str) -> Optional[AuthChallenge]:
        return self.model.query.filter_by(token=token).first()

    def delete_open_for_user(self, user_id: int, purpose: str) -> None:
        rows = self.model.query.filter_by(
            user_id=user_id,
            purpose=purpose,
            consumed_at=None,
        ).all()
        for row in rows:
            self.delete(row)

    def delete_open_for_pending(self, pending_id: int, purpose: str) -> None:
        rows = self.model.query.filter_by(
            pending_registration_id=pending_id,
            purpose=purpose,
            consumed_at=None,
        ).all()
        for row in rows:
            self.delete(row)

    def claim(
        self,
        token: str,
        expected_digest: str,
        now: datetime,
        max_attempts: int,
    ) -> bool:
        """Atomically mark one matching live challenge consumed."""
        result = self.db.session.execute(
            update(self.model)
            .where(
                self.model.token == token,
                self.model.code_digest == expected_digest,
                self.model.consumed_at.is_(None),
                self.model.expires_at >= now,
                self.model.failed_attempts < max_attempts,
            )
            .values(consumed_at=now)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def record_failed_attempt(
        self,
        token: str,
        now: datetime,
        max_attempts: int,
    ) -> bool:
        result = self.db.session.execute(
            update(self.model)
            .where(
                self.model.token == token,
                self.model.consumed_at.is_(None),
                self.model.expires_at >= now,
                self.model.failed_attempts < max_attempts,
            )
            .values(failed_attempts=self.model.failed_attempts + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
