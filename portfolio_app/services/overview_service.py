"""Overview service for portfolio-level analytics and dashboard totals."""

from decimal import Decimal
from typing import Dict, List, Tuple, Any
from portfolio_app.repositories.portfolio_repository import PortfolioRepository
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class OverviewService:
    """Service for portfolio-level analytics (overview dashboard, charts)."""

    def __init__(self, portfolio_repo: PortfolioRepository, user_id=None):
        self.portfolio_repo = portfolio_repo
        self._user_id = user_id

    def get_portfolio_summary(self) -> Tuple[List[Dict[str, Any]], Decimal]:
        return PortfolioCalculator.get_portfolio_summary(user_id=self._user_id)

    def get_portfolio_dashboard_totals(self) -> Dict[str, Any]:
        return PortfolioCalculator.get_portfolio_dashboard_totals(user_id=self._user_id)

    def get_symbol_performance(self) -> List[Dict[str, Any]]:
        """Per-(portfolio, symbol) realized performance for charts/heatmaps."""
        return PortfolioCalculator.get_user_symbol_performance(user_id=self._user_id)
