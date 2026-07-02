"""PortfolioEvent repository for database operations on PortfolioEvent model."""

from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.portfolio_event import PortfolioEvent
from portfolio_app.models.portfolio import Portfolio


class PortfolioEventRepository(BaseRepository[PortfolioEvent]):
    """Repository for PortfolioEvent model — all queries are scoped to a single user."""

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _scoped(self, query):
        if self._user_id is not None:
            query = query.join(Portfolio, PortfolioEvent.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == self._user_id)
        return query

    def get_by_id(self, id: int) -> Optional[PortfolioEvent]:
        return self._scoped(self.model.query.filter(PortfolioEvent.id == id)).first()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[PortfolioEvent]:
        return self._scoped(
            self.model.query.filter(PortfolioEvent.portfolio_id == portfolio_id)
        ).order_by(PortfolioEvent.date.asc()).all()
