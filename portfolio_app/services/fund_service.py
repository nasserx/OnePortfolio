"""Portfolio service for portfolio CRUD and event business logic."""

from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.fund import Portfolio
from portfolio_app.models.fund_event import PortfolioEvent
from portfolio_app.repositories.fund_repository import PortfolioRepository
from portfolio_app.repositories.fund_event_repository import PortfolioEventRepository
from portfolio_app.utils.constants import EventType
from portfolio_app.utils.decimal_utils import ZERO, to_decimal as _to_decimal
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator


class PortfolioService:
    """Service for portfolio CRUD and event business logic."""

    def __init__(self, portfolio_repo: PortfolioRepository, portfolio_event_repo: PortfolioEventRepository):
        self.portfolio_repo = portfolio_repo
        self.portfolio_event_repo = portfolio_event_repo

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------

    def create_portfolio(self, name: str, user_id: Optional[int] = None) -> Portfolio:
        """Create a new portfolio with zero balance."""
        if self.portfolio_repo.get_by_name(name):
            raise ValueError('A portfolio with this name already exists')

        portfolio = Portfolio(name=name, net_deposits=ZERO, user_id=user_id)
        self.portfolio_repo.add(portfolio)
        self.portfolio_repo.commit()
        return portfolio

    def delete_portfolio(self, portfolio_id: int) -> str:
        """Delete portfolio and cascade-delete its events and transactions."""
        portfolio = self._require_portfolio(portfolio_id)
        name = portfolio.name
        self.portfolio_repo.delete(portfolio)
        self.portfolio_repo.commit()
        return name

    # ------------------------------------------------------------------
    # Deposit / Withdraw
    # ------------------------------------------------------------------

    def deposit_funds(self, portfolio_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Portfolio:
        """Deposit funds into a portfolio."""
        portfolio = self._require_portfolio(portfolio_id)
        portfolio.net_deposits = _to_decimal(portfolio.net_deposits) + amount_delta
        self._create_event(portfolio_id, EventType.DEPOSIT, amount_delta, notes, date)
        self.portfolio_repo.commit()
        return portfolio

    def withdraw_funds(self, portfolio_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Portfolio:
        """Withdraw funds from a portfolio (amount_delta is positive)."""
        portfolio = self._require_portfolio(portfolio_id)
        available_cash = PortfolioCalculator.get_available_cash_for_portfolio(portfolio_id)
        if amount_delta > available_cash:
            raise ValueError('Insufficient funds')
        portfolio.net_deposits = _to_decimal(portfolio.net_deposits) - amount_delta
        self._create_event(portfolio_id, EventType.WITHDRAWAL, -amount_delta, notes, date)
        self.portfolio_repo.commit()
        return portfolio

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    def update_portfolio_event(self, event_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> PortfolioEvent:
        """Update a portfolio event and adjust the parent portfolio's balance."""
        event = self._require_event(event_id)
        portfolio = self._require_portfolio(event.portfolio_id)

        old_delta = _to_decimal(event.amount_delta)
        delta_change = amount_delta - old_delta
        portfolio.net_deposits = _to_decimal(portfolio.net_deposits) + delta_change

        event.amount_delta = amount_delta
        if notes is not None:
            event.notes = notes
        if date is not None:
            event.date = date

        self.portfolio_repo.commit()
        return event

    def delete_portfolio_event(self, event_id: int) -> int:
        """Delete a portfolio event and reverse its effect on the balance."""
        event = self._require_event(event_id)
        portfolio_id = event.portfolio_id

        portfolio = self._require_portfolio(portfolio_id)
        portfolio.net_deposits = _to_decimal(portfolio.net_deposits) - _to_decimal(event.amount_delta)

        self.portfolio_event_repo.delete(event)
        self.portfolio_repo.commit()
        return portfolio_id

    # ------------------------------------------------------------------
    # Backward-compatible aliases (used during transition)
    # ------------------------------------------------------------------

    def create_fund(self, name: str, user_id: Optional[int] = None) -> Portfolio:
        return self.create_portfolio(name=name, user_id=user_id)

    def delete_fund(self, portfolio_id: int) -> str:
        return self.delete_portfolio(portfolio_id)

    def update_fund_event(self, event_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> PortfolioEvent:
        return self.update_portfolio_event(event_id=event_id, amount_delta=amount_delta, notes=notes, date=date)

    def delete_fund_event(self, event_id: int) -> int:
        return self.delete_portfolio_event(event_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_portfolio(self, portfolio_id: int) -> Portfolio:
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError('Portfolio not found')
        return portfolio

    def _require_event(self, event_id: int) -> PortfolioEvent:
        event = self.portfolio_event_repo.get_by_id(event_id)
        if not event:
            raise ValueError('Event not found')
        return event

    def _create_event(self, portfolio_id: int, event_type: str, amount_delta: Decimal, notes: Optional[str], date: Optional[Any] = None) -> PortfolioEvent:
        event = PortfolioEvent(
            portfolio_id=portfolio_id,
            event_type=event_type,
            amount_delta=amount_delta,
            notes=notes
        )
        if date is not None:
            event.date = date
        self.portfolio_event_repo.add(event)
        return event


# Backward-compatible alias.
FundService = PortfolioService
