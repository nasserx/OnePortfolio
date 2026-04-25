"""Dividend repository for database operations on Dividend model."""

from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.utils.decimal_utils import ZERO
from decimal import Decimal


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

    def get_by_portfolio_and_symbol(self, portfolio_id: int, symbol: str) -> List[Dividend]:
        return self._scoped(
            self.model.query.filter(
                Dividend.portfolio_id == portfolio_id,
                Dividend.symbol == symbol.upper(),
            )
        ).order_by(Dividend.date.desc()).all()

    def get_by_id_for_portfolio(self, dividend_id: int, portfolio_id: int) -> Optional[Dividend]:
        return self._scoped(
            self.model.query.filter(
                Dividend.id == dividend_id,
                Dividend.portfolio_id == portfolio_id,
            )
        ).first()

    def get_total_for_portfolio(self, portfolio_id: int) -> Decimal:
        from sqlalchemy import func
        result = self._scoped(
            self.model.query
            .with_entities(func.sum(Dividend.amount))
            .filter(Dividend.portfolio_id == portfolio_id)
        ).scalar()
        return Decimal(str(result)) if result else ZERO
