"""One scoped prospective cash-policy boundary for all mutations.

Validation happens before ORM fields are changed; a rejected proposal cannot
leak into the session through autoflush. Daily balances are never persisted.
"""

from datetime import datetime, timezone
from functools import wraps
from types import SimpleNamespace

from portfolio_app import db
from portfolio_app.calculators.daily_cash import CashFact, cash_day, build_daily_cash_ledger, permits_cash_mutation
from portfolio_app.calculators.financial_math import transaction_cash_effect
from portfolio_app.models.transaction import Transaction
from portfolio_app.models.portfolio_event import PortfolioEvent
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.portfolio_transfer import PortfolioTransfer
from portfolio_app.utils.decimal_utils import ZERO, withdrawal_max_text
from portfolio_app.utils.messages import MESSAGES


def cash_mutation(method):
    """Serialize SQLite validation-through-commit, not read-only ledger queries.

    SQLite's deferred driver transaction otherwise allows two readers to approve
    spending the same cash. Acquire the writer reservation BEFORE service reads.
    Existing active DB transactions must already be write transactions; service
    callers normally enter with only an SQLAlchemy logical/autobegin transaction.
    """
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            connection = db.session.connection()
            if connection.dialect.name == 'sqlite':
                driver = connection.connection.driver_connection
                if not driver.in_transaction:
                    connection.exec_driver_sql('BEGIN IMMEDIATE')
                # Routes can have loaded a record before entering the service.
                # Refresh clean identity-map rows only; never discard pending work.
                if not (db.session.new or db.session.dirty or db.session.deleted):
                    db.session.expire_all()
            result = method(*args, **kwargs)
            # No-op edits return early without the method's usual commit.
            if connection.dialect.name == 'sqlite' and driver.in_transaction:
                db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise
    return guarded


def new_effective_date(value):
    """Resolve the existing UTC-now default once, before validation and storage."""
    if value is not None and not isinstance(value, datetime):
        raise ValueError('A valid effective date is required.')
    return value if value is not None else datetime.now(timezone.utc)


def cash_fact(record, *, portfolio_id=None, **changes):
    """Immutable raw-fact proposal, including edits, without dirtying the ORM."""
    effective_date = changes.get('date', record.date)
    if isinstance(record, PortfolioTransfer):
        source = changes.get('source_portfolio_id', record.source_portfolio_id)
        destination = changes.get('destination_portfolio_id', record.destination_portfolio_id)
        if portfolio_id not in (source, destination):
            raise ValueError('Portfolio is not a transfer endpoint')
        component = 'transfer_out' if portfolio_id == source else 'transfer_in'
        amount = changes.get('amount', record.amount)
    elif isinstance(record, Transaction):
        row = SimpleNamespace(**{
            key: changes.get(key, getattr(record, key))
            for key in ('transaction_type', 'price', 'quantity', 'fees')
        })
        effect = transaction_cash_effect(row)
        component = 'buy_outflows' if row.transaction_type == 'Buy' else 'net_sale_proceeds'
        amount = effect.copy_negate() if row.transaction_type == 'Buy' else effect
    elif isinstance(record, PortfolioEvent):
        amount = changes.get('amount_delta', record.amount_delta)
        component = 'withdrawals' if amount < ZERO else 'funding_inflows'
        amount = amount.copy_abs()
    elif isinstance(record, Dividend):
        component, amount = 'dividends', changes.get('amount', record.amount)
    else:
        raise TypeError('Unsupported cash record')
    return CashFact(cash_day(effective_date), component, amount)


class CashAccount:
    def __init__(self, portfolio_repo):
        self.portfolio_repo = portfolio_repo

    def _records(self, portfolio_id):
        if not self.portfolio_repo.get_by_id(portfolio_id):
            raise ValueError(MESSAGES['PORTFOLIO_NOT_FOUND'])
        records = [row for model in (PortfolioEvent, Transaction, Dividend)
                for row in model.query.filter_by(portfolio_id=portfolio_id).all()]
        # Ownership was checked above. Include every linked cash effect; do not
        # hide malformed legacy links from validation simply by filtering a side.
        records.extend(PortfolioTransfer.query.filter(
            (PortfolioTransfer.source_portfolio_id == portfolio_id) |
            (PortfolioTransfer.destination_portfolio_id == portfolio_id),
        ).all())
        return records

    def ledger(self, portfolio_id):
        return build_daily_cash_ledger(cash_fact(row, portfolio_id=portfolio_id) for row in self._records(portfolio_id))

    def validate(self, portfolio_id, *, remove=(), add=(), message=None):
        records = self._records(portfolio_id)
        removed = {(type(row), row.id) for row in remove}
        before = build_daily_cash_ledger(cash_fact(row, portfolio_id=portfolio_id) for row in records)
        after = build_daily_cash_ledger([
            *(cash_fact(row, portfolio_id=portfolio_id) for row in records if (type(row), row.id) not in removed), *add,
        ])
        if not permits_cash_mutation(before, after):
            raise ValueError(message or MESSAGES['CASH_ALREADY_SPENT'])
        return after

    def withdrawal_max(self, portfolio_id, effective_date=None):
        return withdrawal_max_text(self.ledger(portfolio_id).maximum_withdrawal(
            new_effective_date(effective_date),
        ))
