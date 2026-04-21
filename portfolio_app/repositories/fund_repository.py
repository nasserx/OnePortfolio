"""Portfolio repository for database operations on Portfolio model."""

from typing import Optional, List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.fund import Portfolio


class PortfolioRepository(BaseRepository[Portfolio]):
    """Repository for Portfolio model — all queries are scoped to a single user."""

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _base_query(self):
        q = self.model.query
        if self._user_id is not None:
            q = q.filter_by(user_id=self._user_id)
        return q

    def get_all(self) -> List[Portfolio]:
        return self._base_query().all()

    def get_by_id(self, id: int) -> Optional[Portfolio]:
        return self._base_query().filter_by(id=id).first()

    def get_by_name(self, name: str) -> Optional[Portfolio]:
        return self._base_query().filter_by(name=name).first()

    def get_existing_names(self) -> List[str]:
        return [p.name for p in self.get_all()]


# Backward-compatible alias.
FundRepository = PortfolioRepository
