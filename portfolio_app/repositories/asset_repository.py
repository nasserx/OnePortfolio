"""Asset repository for database operations on Asset model."""

from typing import Optional, List
from portfolio_app.repositories.base import BaseRepository
from portfolio_app.models.asset import Asset


class AssetRepository(BaseRepository[Asset]):
    """Repository for Asset model database operations."""

    def get_by_portfolio_and_symbol(self, portfolio_id: int, symbol: str) -> Optional[Asset]:
        """Get asset by portfolio ID and symbol."""
        return self.model.query.filter_by(
            portfolio_id=portfolio_id,
            symbol=symbol.strip().upper()
        ).first()

    def get_by_portfolio_id(self, portfolio_id: int) -> List[Asset]:
        """Get all assets for a specific portfolio."""
        return self.model.query.filter_by(portfolio_id=portfolio_id).all()

    # Backward-compatible aliases.
    def get_by_fund_and_symbol(self, fund_id: int, symbol: str) -> Optional[Asset]:
        return self.get_by_portfolio_and_symbol(fund_id, symbol)

    def get_by_fund_id(self, fund_id: int) -> List[Asset]:
        return self.get_by_portfolio_id(fund_id)
