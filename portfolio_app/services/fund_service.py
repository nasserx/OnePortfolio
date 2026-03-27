"""Fund service for fund-related business logic."""

from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.fund import Fund
from portfolio_app.models.fund_event import FundEvent
from portfolio_app.repositories.fund_repository import FundRepository
from portfolio_app.repositories.fund_event_repository import FundEventRepository
from portfolio_app.utils.constants import EventType

ZERO = Decimal('0')


def _to_decimal(value) -> Decimal:
    """Convert any numeric value to Decimal safely."""
    return Decimal(str(value))


class FundService:
    """Service for fund-related business logic."""

    def __init__(self, fund_repo: FundRepository, event_repo: FundEventRepository):
        self.fund_repo = fund_repo
        self.event_repo = event_repo

    # ------------------------------------------------------------------
    # Fund CRUD
    # ------------------------------------------------------------------

    def create_fund(self, asset_class: str, amount: Decimal, user_id: Optional[int] = None, notes: str = 'Initial funding', date: Optional[Any] = None) -> Fund:
        """Create new fund with initial deposit event.

        Args:
            asset_class: Asset class name (e.g. 'Stocks', 'Crypto')
            amount: Initial deposit amount
            user_id: Owner user ID
            notes: Label for the initial deposit event
            date: Date of the initial deposit event
        """
        if self.fund_repo.get_by_asset_class(asset_class):
            raise ValueError('Fund already exists')

        fund = Fund(asset_class=asset_class, cash_balance=amount, user_id=user_id)
        self.fund_repo.add(fund)
        self.fund_repo.flush()  # Obtain fund.id before creating event

        event = FundEvent(
            fund_id=fund.id,
            event_type=EventType.INITIAL,
            amount_delta=amount,
            notes=notes
        )
        if date is not None:
            event.date = date
        self.event_repo.add(event)
        self.fund_repo.commit()

        return fund

    def delete_fund(self, fund_id: int) -> str:
        """Delete fund and cascade-delete its events and transactions.

        Returns:
            The asset class name of the deleted fund.
        """
        fund = self._require_fund(fund_id)
        asset_class = fund.asset_class
        self.fund_repo.delete(fund)
        self.fund_repo.commit()
        return asset_class

    # ------------------------------------------------------------------
    # Deposit / Withdraw
    # ------------------------------------------------------------------

    def deposit_funds(self, fund_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Fund:
        """Deposit funds into an asset class."""
        fund = self._require_fund(fund_id)
        fund.cash_balance = _to_decimal(fund.cash_balance) + amount_delta
        self._create_event(fund_id, EventType.DEPOSIT, amount_delta, notes, date)
        self.fund_repo.commit()
        return fund

    def withdraw_funds(self, fund_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Fund:
        """Withdraw funds from an asset class (amount_delta is positive)."""
        fund = self._require_fund(fund_id)
        fund.cash_balance = _to_decimal(fund.cash_balance) - amount_delta
        # Store withdrawal as negative delta for accurate fund history
        self._create_event(fund_id, EventType.WITHDRAWAL, -amount_delta, notes, date)
        self.fund_repo.commit()
        return fund

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    def update_fund_event(self, event_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> FundEvent:
        """Update a fund event and adjust the parent fund's balance."""
        event = self._require_event(event_id)

        # Apply the difference between old and new delta to the fund balance
        old_delta = _to_decimal(event.amount_delta)
        delta_change = amount_delta - old_delta

        fund = self.fund_repo.get_by_id(event.fund_id)
        if fund:
            fund.cash_balance = _to_decimal(fund.cash_balance) + delta_change

        event.amount_delta = amount_delta
        if notes is not None:
            event.notes = notes
        if date is not None:
            event.date = date

        self.fund_repo.commit()
        return event

    def delete_fund_event(self, event_id: int) -> int:
        """Delete a fund event, reverse its effect, and clean up empty events.

        After deletion, if only zero-delta events remain (no financial impact),
        they are removed as well. The fund itself is kept with its current balance.
        """
        event = self._require_event(event_id)
        fund_id = event.fund_id

        # Reverse the event's effect on the fund balance
        fund = self.fund_repo.get_by_id(fund_id)
        if fund:
            fund.cash_balance = _to_decimal(fund.cash_balance) - _to_decimal(event.amount_delta)

        self.event_repo.delete(event)
        self.event_repo.flush()

        # Auto-cleanup: remove leftover zero-delta events (no useful history)
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
        """Remove all remaining events if they all have zero delta (no financial data)."""
        remaining = self.event_repo.get_by_fund_id(fund_id)
        if remaining and all(_to_decimal(e.amount_delta) == ZERO for e in remaining):
            for e in remaining:
                self.event_repo.delete(e)
