"""Atomic transfer mutations, with prospective validation of every affected owner portfolio."""

from portfolio_app.models import PortfolioTransfer
from portfolio_app.services.cash_account import CashAccount, cash_fact, new_effective_date
from portfolio_app.services.mutation import financial_mutation
from portfolio_app.utils.decimal_utils import ZERO, parse_financial_decimal
from portfolio_app.utils.messages import MESSAGES


class TransferService:
    def __init__(self, portfolio_repo, transfer_repo):
        self.portfolio_repo = portfolio_repo
        self.transfer_repo = transfer_repo
        self.cash_account = CashAccount(portfolio_repo)

    def _require_portfolios(self, source, destination):
        # Same generic error for absent, foreign-owned or unauthenticated targets.
        portfolios = [self.portfolio_repo.get_by_id(identifier) for identifier in (source, destination)]
        if self.portfolio_repo.user_id is None or any(row is None for row in portfolios):
            raise ValueError(MESSAGES['TRANSFER_PORTFOLIO_INVALID'])
        source, destination = (row.id for row in portfolios)
        if source == destination:
            raise ValueError(MESSAGES['TRANSFER_SAME_PORTFOLIO'])
        return source, destination

    def _require_transfer(self, identifier):
        transfer = self.transfer_repo.get_by_id(identifier) if self.portfolio_repo.user_id is not None else None
        if transfer is None:
            raise ValueError(MESSAGES['TRANSFER_NOT_FOUND'])
        return transfer

    def _proposal(self, source, destination, amount, date, notes):
        source, destination = self._require_portfolios(source, destination)
        amount = parse_financial_decimal(amount)
        if amount <= ZERO:
            raise ValueError(MESSAGES['VALUE_POSITIVE'])
        return PortfolioTransfer(source_portfolio_id=source, destination_portfolio_id=destination,
                                 amount=amount, date=new_effective_date(date), notes=notes or None)

    def _validate(self, old=None, new=None):
        endpoints = {pid for row in (old, new) if row is not None
                     for pid in (row.source_portfolio_id, row.destination_portfolio_id)}
        for pid in sorted(endpoints):
            removed = (old,) if old is not None and pid in (old.source_portfolio_id, old.destination_portfolio_id) else ()
            added = (cash_fact(new, portfolio_id=pid),) if new is not None and pid in (
                new.source_portfolio_id, new.destination_portfolio_id,
            ) else ()
            self.cash_account.validate(pid, remove=removed, add=added, message=MESSAGES['TRANSFER_EXCEEDS_CASH'])

    @financial_mutation
    def create(self, source_portfolio_id, destination_portfolio_id, amount, date=None, notes=''):
        row = self._proposal(source_portfolio_id, destination_portfolio_id, amount, date, notes)
        self._validate(new=row)
        self.transfer_repo.add(row)
        return row

    @financial_mutation
    def update(self, transfer_id, *, source_portfolio_id=None, destination_portfolio_id=None,
               amount=None, date=None, notes=None):
        row = self._require_transfer(transfer_id)
        proposal = self._proposal(
            source_portfolio_id if source_portfolio_id is not None else row.source_portfolio_id,
            destination_portfolio_id if destination_portfolio_id is not None else row.destination_portfolio_id,
            amount if amount is not None else row.amount,
            date if date is not None else row.date, notes if notes is not None else row.notes,
        )
        self._validate(old=row, new=proposal)
        for field in ('source_portfolio_id', 'destination_portfolio_id', 'amount', 'date', 'notes'):
            setattr(row, field, getattr(proposal, field))
        return row

    @financial_mutation
    def delete(self, transfer_id):
        row = self._require_transfer(transfer_id)
        self._validate(old=row)
        self.transfer_repo.delete(row)
