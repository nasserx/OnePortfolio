"""Symbol repository for database operations on Symbol model."""

from typing import Optional, List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.symbol import Symbol


class SymbolRepository(BaseRepository[Symbol]):
    """Repository for Symbol model database operations."""

    def get_by_portfolio_and_ticker(self, portfolio_id: int, symbol: str) -> Optional[Symbol]:
        """Get the tracked-symbol row for a portfolio/ticker pair."""
        return self.model.query.filter_by(
            portfolio_id=portfolio_id,
            symbol=symbol.strip().upper()
        ).first()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Symbol]:
        """Get all tracked symbols for a specific portfolio."""
        return self.model.query.filter_by(portfolio_id=portfolio_id).all()
