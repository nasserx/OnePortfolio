"""Symbol repository for database operations on Symbol model."""

from typing import Optional, List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.symbol import Symbol
from portfolio_app.models.portfolio import Portfolio


class SymbolRepository(BaseRepository[Symbol]):
    """Repository for Symbol model — all queries are scoped to a single user."""

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _scoped(self, query):
        if self._user_id is not None:
            query = query.join(Portfolio, Symbol.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == self._user_id)
        return query

    def get_by_id(self, id: int) -> Optional[Symbol]:
        return self._scoped(self.model.query.filter(Symbol.id == id)).first()

    def get_by_portfolio_and_ticker(self, portfolio_id: int, symbol: str) -> Optional[Symbol]:
        return self._scoped(
            self.model.query.filter(
                Symbol.portfolio_id == portfolio_id,
                Symbol.symbol == symbol.strip().upper(),
            )
        ).first()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Symbol]:
        return self._scoped(
            self.model.query.filter(Symbol.portfolio_id == portfolio_id)
        ).all()
