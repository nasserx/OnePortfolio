"""Portfolio service for portfolio-level operations."""

from decimal import Decimal
from typing import Dict, List, Tuple, Any
from portfolio_app.repositories.fund_repository import FundRepository
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class PortfolioService:
    """Service for portfolio-level operations and summaries."""

    def __init__(self, fund_repo: FundRepository, user_id=None):
        self.fund_repo = fund_repo
        self._user_id = user_id

    def get_portfolio_summary(self) -> Tuple[List[Dict[str, Any]], Decimal]:
        return PortfolioCalculator.get_category_summary(user_id=self._user_id)

    def get_portfolio_dashboard_totals(self) -> Dict[str, Any]:
        return PortfolioCalculator.get_portfolio_dashboard_totals(user_id=self._user_id)
