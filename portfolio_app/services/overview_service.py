"""Overview service for portfolio-level analytics and dashboard totals."""

from decimal import Decimal
from typing import Dict, List, Tuple, Any
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.calculators.financial_math import calculate_portfolio_metrics, calculate_cumulative_return
from portfolio_app.utils.financial_arithmetic import exact_sum, exact_subtract


class OverviewService:
    """Service for portfolio-level analytics (overview dashboard, charts)."""

    def __init__(self, user_id=None):
        self._user_id = user_id

    @staticmethod
    def get_landing_preview():
        """Public synthetic example; no database reads or client-side return math."""
        portfolios = [
            {'name': name, 'bookValue': Decimal(value)}
            for name, value in (('Stocks', '18400'), ('ETFs', '14200'), ('Crypto', '9580'))
        ]
        book_value = exact_sum(p['bookValue'] for p in portfolios)
        cash = Decimal('6320')
        metrics = calculate_portfolio_metrics(
            cash, exact_subtract(book_value, cash), Decimal('3640'), Decimal('2410'), Decimal('28000'),
        )
        metrics['cash_balance'] = cash
        metrics['net_contributions'] = exact_subtract(book_value, metrics['total_realized_earnings'])
        metrics['paid_in_capital'] = Decimal('48000')  # External deposits before withdrawals.
        metrics['capital_return'] = calculate_cumulative_return(
            metrics['total_realized_earnings'], metrics['paid_in_capital'],
        )
        return {'portfolios': portfolios, 'metrics': metrics}

    def get_portfolio_summary(self) -> Tuple[List[Dict[str, Any]], Decimal]:
        return self.get_financial_snapshot().as_portfolio_summary()

    def get_financial_snapshot(self):
        """One fresh read model for a composed dashboard response."""
        return PortfolioCalculator.get_financial_snapshot(user_id=self._user_id)

    def get_portfolio_dashboard_totals(self) -> Dict[str, Any]:
        return dict(self.get_financial_snapshot().totals)

    def get_symbol_financials(self) -> List[Dict[str, Any]]:
        """Canonical per-asset earnings and returns, including retained trading fields."""
        return PortfolioCalculator.get_user_symbol_financials(user_id=self._user_id)
