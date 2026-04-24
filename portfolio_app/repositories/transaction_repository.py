"""Transaction repository for database operations on Transaction model."""

from typing import List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.transaction import Transaction


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for Transaction model database operations."""

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Transaction]:
        """Get all transactions for a specific portfolio."""
        return self.model.query.filter_by(portfolio_id=portfolio_id).all()

    def get_by_symbol(self, portfolio_id: int, symbol: str) -> List[Transaction]:
        """Get all transactions for a specific symbol in a portfolio."""
        return self.model.query.filter_by(
            portfolio_id=portfolio_id,
            symbol=symbol.strip().upper()
        ).order_by(Transaction.date.asc()).all()
