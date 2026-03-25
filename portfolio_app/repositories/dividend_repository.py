"""Dividend repository for database operations on Dividend model."""

from decimal import Decimal
from typing import List, Optional
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.dividend import Dividend

ZERO = Decimal('0')


class DividendRepository(BaseRepository[Dividend]):
    """Repository for Dividend model database operations."""

    def get_by_fund_id(self, fund_id: int) -> List[Dividend]:
        """Return all dividends for a fund, newest first."""
        return (
            self.model.query
            .filter_by(fund_id=fund_id)
            .order_by(Dividend.date.desc())
            .all()
        )

    def get_by_id_for_fund(self, dividend_id: int, fund_id: int) -> Optional[Dividend]:
        """Return a dividend only if it belongs to the given fund (ownership check)."""
        return (
            self.model.query
            .filter_by(id=dividend_id, fund_id=fund_id)
            .first()
        )

    def get_total_for_fund(self, fund_id: int) -> Decimal:
        """Return the sum of all dividend amounts for a fund."""
        from sqlalchemy import func
        result = (
            self.model.query
            .with_entities(func.sum(Dividend.amount))
            .filter_by(fund_id=fund_id)
            .scalar()
        )
        return Decimal(str(result)) if result else ZERO
