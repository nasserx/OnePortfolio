"""Portfolio service for portfolio CRUD and cash-event business logic."""

from decimal import Decimal
from typing import Optional, Any
from portfolio_app.models.portfolio import Portfolio
from portfolio_app.models.portfolio_event import PortfolioEvent
from portfolio_app.models.portfolio_transfer import PortfolioTransfer
from portfolio_app.repositories.portfolio_repository import PortfolioRepository
from portfolio_app.repositories.portfolio_event_repository import PortfolioEventRepository
from portfolio_app.utils.constants import EventType
from portfolio_app.utils.decimal_utils import ZERO, parse_financial_decimal
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.services.cash_account import CashAccount, cash_fact, new_effective_date
from portfolio_app.services.mutation import financial_mutation


class PortfolioService:
    """Service for portfolio CRUD and cash-event business logic."""

    def __init__(self, portfolio_repo: PortfolioRepository, portfolio_event_repo: PortfolioEventRepository):
        self.portfolio_repo = portfolio_repo
        self.portfolio_event_repo = portfolio_event_repo
        self.cash_account = CashAccount(portfolio_repo)

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------

    @financial_mutation
    def create_portfolio(self, name: str, user_id: Optional[int] = None) -> Portfolio:
        """Create a new portfolio."""
        owner_id = self.portfolio_repo.user_id
        if owner_id is not None:
            if user_id not in (None, owner_id):
                raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])
            user_id = owner_id
        if self.portfolio_repo.get_by_name(name):
            raise ValueError(MESSAGES['PORTFOLIO_NAME_TAKEN'])

        portfolio = Portfolio(name=name, user_id=user_id)
        self.portfolio_repo.add(portfolio)
        return portfolio

    @financial_mutation
    def rename_portfolio(self, portfolio_id: int, name: str) -> Portfolio:
        """Rename a tenant-owned portfolio without changing its identity."""
        portfolio = self._require_portfolio(portfolio_id)
        normalized_name = name.strip()
        normalized_lower = normalized_name.lower()

        if normalized_lower == portfolio.name.lower():
            return portfolio

        if any(
            existing.id != portfolio.id and existing.name.lower() == normalized_lower
            for existing in self.portfolio_repo.get_all()
        ):
            raise ValueError(MESSAGES['PORTFOLIO_NAME_TAKEN'])

        portfolio.name = normalized_name
        return portfolio

    @financial_mutation
    def delete_portfolio(self, portfolio_id: int) -> str:
        """Delete portfolio and cascade-delete its events and transactions."""
        portfolio = self._require_portfolio(portfolio_id)
        name = portfolio.name
        if PortfolioTransfer.query.filter(
            (PortfolioTransfer.source_portfolio_id == portfolio_id) |
            (PortfolioTransfer.destination_portfolio_id == portfolio_id),
        ).first():
            raise ValueError(MESSAGES['PORTFOLIO_HAS_TRANSFERS'])
        self.portfolio_repo.delete(portfolio)
        return name

    # ------------------------------------------------------------------
    # Deposit / Withdraw
    # ------------------------------------------------------------------

    @financial_mutation
    def deposit_funds(self, portfolio_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Portfolio:
        """Deposit funds into a portfolio."""
        amount_delta = parse_financial_decimal(amount_delta)
        portfolio = self._require_portfolio(portfolio_id)
        self._create_event(portfolio_id, EventType.DEPOSIT, amount_delta, notes, date)
        return portfolio

    @financial_mutation
    def withdraw_funds(self, portfolio_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> Portfolio:
        """Withdraw funds from a portfolio (amount_delta is positive)."""
        amount_delta = parse_financial_decimal(amount_delta)
        portfolio = self._require_portfolio(portfolio_id)
        self._create_event(portfolio_id, EventType.WITHDRAWAL, amount_delta.copy_negate(), notes, date)
        return portfolio

    # ------------------------------------------------------------------
    # Cash-event operations
    # ------------------------------------------------------------------

    @financial_mutation
    def update_portfolio_event(self, event_id: int, amount_delta: Decimal, notes: Optional[str] = None, date: Optional[Any] = None) -> PortfolioEvent:
        """Validate the complete prospective cash history before changing raw facts."""
        amount_delta = parse_financial_decimal(amount_delta)
        event = self._require_event(event_id)
        self._require_portfolio(event.portfolio_id)

        if (event.event_type == EventType.WITHDRAWAL and amount_delta >= ZERO) or (
            event.event_type != EventType.WITHDRAWAL and amount_delta <= ZERO
        ):
            raise ValueError(MESSAGES['VALUE_POSITIVE'])

        self.cash_account.validate(
            event.portfolio_id, remove=(event,),
            add=(cash_fact(event, amount_delta=amount_delta,
                           date=date if date is not None else event.date),),
            message=MESSAGES['WITHDRAWAL_EXCEEDS_CASH'] if event.event_type == 'Withdrawal' else None,
        )

        event.amount_delta = amount_delta
        if notes is not None:
            event.notes = notes
        if date is not None:
            event.date = date

        return event

    @financial_mutation
    def delete_portfolio_event(self, event_id: int) -> int:
        """Delete only when the prospective daily cash history permits it."""
        event = self._require_event(event_id)
        portfolio_id = event.portfolio_id
        self._require_portfolio(portfolio_id)

        self.cash_account.validate(portfolio_id, remove=(event,))

        self.portfolio_event_repo.delete(event)
        return portfolio_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_portfolio(self, portfolio_id: int) -> Portfolio:
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])
        return portfolio

    def _require_event(self, event_id: int) -> PortfolioEvent:
        event = self.portfolio_event_repo.get_by_id(event_id)
        if not event:
            raise ValueError(MESSAGES['CASH_EVENT_NOT_FOUND'])
        return event

    def _create_event(self, portfolio_id: int, event_type: str, amount_delta: Decimal, notes: Optional[str], date: Optional[Any] = None) -> PortfolioEvent:
        event = PortfolioEvent(
            portfolio_id=portfolio_id,
            event_type=event_type,
            amount_delta=amount_delta,
            notes=notes,
            date=new_effective_date(date),
        )
        if (event_type == EventType.WITHDRAWAL and amount_delta >= ZERO) or (
            event_type != EventType.WITHDRAWAL and amount_delta <= ZERO
        ):
            raise ValueError(MESSAGES['VALUE_POSITIVE'])
        self.cash_account.validate(
            portfolio_id, add=(cash_fact(event),),
            message=MESSAGES['WITHDRAWAL_EXCEEDS_CASH'] if event_type == EventType.WITHDRAWAL else None,
        )
        self.portfolio_event_repo.add(event)
        return event
