"""Transaction repository for database operations on Transaction model."""

from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.portfolio import Portfolio


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for Transaction model — all queries are scoped to a single user.

    Every read joins ``Portfolio`` and filters on ``Portfolio.user_id`` so a
    forged ``portfolio_id`` from another user's account silently returns
    nothing instead of leaking rows.
    """

    def __init__(self, model, db, user_id: Optional[int] = None):
        super().__init__(model, db)
        self._user_id = user_id

    def _scoped(self, query):
        if self._user_id is not None:
            query = query.join(Portfolio, Transaction.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == self._user_id)
        return query

    def get_by_id(self, id: int) -> Optional[Transaction]:
        return self._scoped(self.model.query.filter(Transaction.id == id)).first()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Transaction]:
        return self._scoped(
            self.model.query.filter(Transaction.portfolio_id == portfolio_id)
        ).all()

    def get_by_symbol(self, portfolio_id: int, symbol: str) -> List[Transaction]:
        return self._scoped(
            self.model.query.filter(
                Transaction.portfolio_id == portfolio_id,
                Transaction.symbol == symbol.strip().upper(),
            )
        ).order_by(Transaction.date.asc()).all()
