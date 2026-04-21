"""PortfolioEvent repository for database operations on PortfolioEvent model."""

from typing import List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.fund_event import PortfolioEvent


class PortfolioEventRepository(BaseRepository[PortfolioEvent]):
    """Repository for PortfolioEvent model database operations."""

    def get_by_portfolio_id(self, portfolio_id: int) -> List[PortfolioEvent]:
        """Get all events for a specific portfolio ordered by date."""
        return self.model.query.filter_by(
            portfolio_id=portfolio_id
        ).order_by(PortfolioEvent.date.asc()).all()

    # Backward-compatible alias.
    def get_by_fund_id(self, portfolio_id: int) -> List[PortfolioEvent]:
        return self.get_by_portfolio_id(portfolio_id)


# Backward-compatible alias.
FundEventRepository = PortfolioEventRepository
