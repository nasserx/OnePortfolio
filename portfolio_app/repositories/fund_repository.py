"""Fund repository for database operations on Fund model."""

from typing import Optional, List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.fund import Fund


class FundRepository(BaseRepository[Fund]):
    """Repository for Fund model — all queries are scoped to a single user."""

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _base_query(self):
        """Return a query pre-filtered by the current user."""
        q = self.model.query
        if self._user_id is not None:
            q = q.filter_by(user_id=self._user_id)
        return q

    def get_all(self) -> List[Fund]:
        """Get all funds belonging to the current user."""
        return self._base_query().all()

    def get_by_id(self, id: int) -> Optional[Fund]:
        """Get a fund by ID, scoped to the current user for security."""
        return self._base_query().filter_by(id=id).first()

    def get_by_name(self, name: str) -> Optional[Fund]:
        """Get fund by name within the current user's portfolio."""
        return self._base_query().filter_by(name=name).first()

    def get_existing_names(self) -> List[str]:
        """Get all portfolio names for the current user."""
        return [f.name for f in self.get_all()]
