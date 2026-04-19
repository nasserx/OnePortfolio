"""Portfolio service for portfolio-level operations."""

from decimal import Decimal
from typing import Dict, List, Tuple, Any
from portfolio_app.repositories.fund_repository import FundRepository
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class PortfolioService:
    """Service for portfolio-level operations and summaries."""

    def __init__(self, fund_repo: FundRepository, user_id=None):
        """Initialize service with repository.

        Args:
            fund_repo: Fund repository
            user_id: Current user ID for data isolation
        """
        self.fund_repo = fund_repo
        self._user_id = user_id

    def get_portfolio_summary(self) -> Tuple[List[Dict[str, Any]], Decimal]:
        """Get portfolio summary for all funds.

        Returns:
            Tuple of (category summaries, total portfolio value)
        """
        return PortfolioCalculator.get_category_summary(user_id=self._user_id)

    def get_portfolio_dashboard_totals(self) -> Dict[str, Any]:
        """Get dashboard totals for the entire portfolio.

        Returns:
            Dictionary with total investment, cash, P&L, value, and ROI metrics
        """
        return PortfolioCalculator.get_portfolio_dashboard_totals(user_id=self._user_id)

    def get_category_transactions_summary(self, fund_id: int) -> Dict[str, Any]:
        """Get aggregated transaction summary for a category.

        Args:
            fund_id: Fund ID

        Returns:
            Dictionary with aggregated transaction metrics
        """
        return PortfolioCalculator.get_category_transactions_summary(fund_id)

    def get_symbol_transactions_summary(self, fund_id: int, symbol: str) -> Dict[str, Any]:
        """Get transaction summary for a specific symbol in a category.

        Args:
            fund_id: Fund ID
            symbol: Asset symbol

        Returns:
            Dictionary with symbol-specific transaction metrics
        """
        return PortfolioCalculator.get_symbol_transactions_summary(fund_id, symbol)

    def get_total_portfolio_value(self) -> Decimal:
        """Get total portfolio value.

        Returns:
            Total portfolio value
        """
        return PortfolioCalculator.get_total_portfolio_value(user_id=self._user_id)

    def get_cash_balance_for_fund(self, fund_id: int) -> Decimal:
        """Get current cash balance for a fund.

        Args:
            fund_id: Fund ID

        Returns:
            Cash balance
        """
        return PortfolioCalculator.get_cash_balance_for_fund(fund_id)

    def get_realized_performance_for_fund(self, fund_id: int) -> Dict[str, Decimal]:
        """Get realized performance metrics for a fund.

        Args:
            fund_id: Fund ID

        Returns:
            Dictionary with realized P&L, cost basis, and proceeds
        """
        return PortfolioCalculator.get_realized_performance_for_fund(fund_id)
