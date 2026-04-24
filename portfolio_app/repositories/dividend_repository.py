"""Dividend repository for database operations on Dividend model."""

from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.dividend import Dividend
from portfolio_app.utils.decimal_utils import ZERO
from decimal import Decimal


class DividendRepository(BaseRepository[Dividend]):
    """Repository for Dividend model database operations."""

    def get_by_portfolio_ids(self, portfolio_ids: List[int]) -> List[Dividend]:
        """Return all dividends for multiple portfolios in a single query, newest first."""
        if not portfolio_ids:
            return []
        return (
            self.model.query
            .filter(Dividend.portfolio_id.in_(portfolio_ids))
            .order_by(Dividend.date.desc())
            .all()
        )

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Dividend]:
        """Return all dividends for a portfolio, newest first."""
        return (
            self.model.query
            .filter_by(portfolio_id=portfolio_id)
            .order_by(Dividend.date.desc())
            .all()
        )

    def get_by_portfolio_and_symbol(self, portfolio_id: int, symbol: str) -> List[Dividend]:
        """Return all dividends for a specific symbol within a portfolio, newest first."""
        return (
            self.model.query
            .filter_by(portfolio_id=portfolio_id, symbol=symbol.upper())
            .order_by(Dividend.date.desc())
            .all()
        )

    def get_by_id_for_portfolio(self, dividend_id: int, portfolio_id: int) -> Optional[Dividend]:
        """Return a dividend only if it belongs to the given portfolio."""
        return (
            self.model.query
            .filter_by(id=dividend_id, portfolio_id=portfolio_id)
            .first()
        )

    def get_total_for_portfolio(self, portfolio_id: int) -> Decimal:
        """Return the sum of all dividend amounts for a portfolio."""
        from sqlalchemy import func
        result = (
            self.model.query
            .with_entities(func.sum(Dividend.amount))
            .filter_by(portfolio_id=portfolio_id)
            .scalar()
        )
        return Decimal(str(result)) if result else ZERO
