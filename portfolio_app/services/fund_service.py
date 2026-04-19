"""Fund service for fund-related business logic."""

from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.fund import Fund
from portfolio_app.models.fund_event import FundEvent
from portfolio_app.repositories.fund_repository import FundRepository
from portfolio_app.repositories.fund_event_repository import FundEventRepository
from portfolio_app.utils.constants import EventType
from portfolio_app.utils.decimal_utils import ZERO, to_decimal as _to_decimal


class FundService:
    """Service for fund-related business logic."""

    def __init__(self, fund_repo: FundRepository, event_repo: FundEventRepository):
        self.fund_repo = fund_repo
        self.event_repo = event_repo

    # ------------------------------------------------------------------
    # Fund CRUD
    # ------------------------------------------------------------------

    def create_fund(self, name: str, user_id: Optional[int] = None) -> Fund:
        """Create a new portfolio with zero balance.

        Args:
            name: Portfolio name (must be unique per user)
            user_id: Owner user ID
        """
        if self.fund_repo.get_by_name(name):
            raise ValueError('A portfolio with this name already exists')

        fund = Fund(name=name, cash_balance=ZERO, user_id=user_id)
        self.fund_repo.add(fund)
        self.fund_repo.commit()

        return fund

    def delete_fund(self, fund_id: int) -> str:
        """Delete fund and cascade-delete its events and transactions.

        Returns:
            The name of the deleted fund.
        """
        fund = self._require_fund(fund_id)
        name = fund.name
        self.fund_repo.delete(fund)
        self.fund_repo.commit()
        return name

    # ------------------------------------------------------------------
    # Deposit / Withdraw
    # ------------------------------------------------------------------

    def deposit_funds(self, fund_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Fund:
        """Deposit funds into a portfolio."""
        fund = self._require_fund(fund_id)
        fund.cash_balance = _to_decimal(fund.cash_balance) + amount_delta
        self._create_event(fund_id, EventType.DEPOSIT, amount_delta, notes, date)
        self.fund_repo.commit()
        return fund

    def withdraw_funds(self, fund_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Fund:
        """Withdraw funds from a portfolio (amount_delta is positive)."""
        fund = self._require_fund(fund_id)
        current_balance = _to_decimal(fund.cash_balance)
        if amount_delta > current_balance:
            raise ValueError('Insufficient cash balance')
        fund.cash_balance = current_balance - amount_delta
        self._create_event(fund_id, EventType.WITHDRAWAL, -amount_delta, notes, date)
        self.fund_repo.commit()
        return fund

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    def update_fund_event(self, event_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> FundEvent:
        """Update a fund event and adjust the parent fund's balance."""
        event = self._require_event(event_id)

        fund = self._require_fund(event.fund_id)

        old_delta = _to_decimal(event.amount_delta)
        delta_change = amount_delta - old_delta

        fund.cash_balance = _to_decimal(fund.cash_balance) + delta_change

        event.amount_delta = amount_delta
        if notes is not None:
            event.notes = notes
        if date is not None:
            event.date = date

        self.fund_repo.commit()
        return event

    def delete_fund_event(self, event_id: int) -> int:
        """Delete a fund event and reverse its effect on the balance."""
        event = self._require_event(event_id)
        fund_id = event.fund_id

        fund = self._require_fund(fund_id)

        fund.cash_balance = _to_decimal(fund.cash_balance) - _to_decimal(event.amount_delta)

        self.event_repo.delete(event)
        self.event_repo.flush()

        self._cleanup_empty_events(fund_id)

        self.fund_repo.commit()
        return fund_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_fund(self, fund_id: int) -> Fund:
        """Fetch fund or raise ValueError."""
        fund = self.fund_repo.get_by_id(fund_id)
        if not fund:
            raise ValueError('Fund not found')
        return fund

    def _require_event(self, event_id: int) -> FundEvent:
        """Fetch event or raise ValueError."""
        event = self.event_repo.get_by_id(event_id)
        if not event:
            raise ValueError('Event not found')
        return event

    def _create_event(self, fund_id: int, event_type: str, amount_delta: Decimal, notes: Optional[str], date: Optional[Any] = None) -> FundEvent:
        """Create and persist a new fund event."""
        event = FundEvent(
            fund_id=fund_id,
            event_type=event_type,
            amount_delta=amount_delta,
            notes=notes
        )
        if date is not None:
            event.date = date
        self.event_repo.add(event)
        return event

    def _cleanup_empty_events(self, fund_id: int) -> None:
        """Remove all remaining events if they all have zero delta."""
        remaining = self.event_repo.get_by_fund_id(fund_id)
        if remaining and all(_to_decimal(e.amount_delta) == ZERO for e in remaining):
            for e in remaining:
                self.event_repo.delete(e)
