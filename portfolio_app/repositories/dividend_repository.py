"""Dividend repository for database operations on Dividend model."""

from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.portfolio import Portfolio


class DividendRepository(BaseRepository[Dividend]):
    """Repository for Dividend model — all queries are scoped to a single user."""

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _scoped(self, query):
        if self._user_id is not None:
            query = query.join(Portfolio, Dividend.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == self._user_id)
        return query

    def get_by_id(self, id: int) -> Optional[Dividend]:
        return self._scoped(self.model.query.filter(Dividend.id == id)).first()

    def get_by_portfolio_ids(self, portfolio_ids: List[int]) -> List[Dividend]:
        if not portfolio_ids:
            return []
        return self._scoped(
            self.model.query.filter(Dividend.portfolio_id.in_(portfolio_ids))
        ).order_by(Dividend.date.desc()).all()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Dividend]:
        return self._scoped(
            self.model.query.filter(Dividend.portfolio_id == portfolio_id)
        ).order_by(Dividend.date.desc()).all()
