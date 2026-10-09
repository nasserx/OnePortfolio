"""Scoped immutable audit reads and internal transaction-bound append support."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from portfolio_app import db
from portfolio_app.models.financial_audit import FinancialAudit
from portfolio_app.models import Portfolio, Transaction, PortfolioEvent, Dividend, PortfolioTransfer, Symbol


# Explicit persisted domain fields; never ORM internals, auth or display values.
AUDITED_FIELDS = {
    Portfolio: ('id', 'user_id', 'name', 'created_at', 'updated_at'),
    Transaction: ('id', 'portfolio_id', 'transaction_type', 'symbol', 'price', 'quantity', 'fees', 'date', 'notes'),
    PortfolioEvent: ('id', 'portfolio_id', 'event_type', 'amount_delta', 'date', 'notes'),
    Dividend: ('id', 'portfolio_id', 'symbol', 'amount', 'date', 'notes', 'created_at'),
    PortfolioTransfer: ('id', 'source_portfolio_id', 'destination_portfolio_id', 'amount', 'date', 'notes', 'created_at', 'updated_at'),
    Symbol: ('id', 'portfolio_id', 'symbol', 'created_at', 'updated_at'),
}


def persisted_state(session, model, identifier):
    """Read actual stored values without autoflush or identity-map substitution."""
    table = model.__table__
    row = session.connection().execute(db.select(*(table.c[name] for name in AUDITED_FIELDS[model]))
                                       .where(table.c.id == identifier)).mappings().first()
    return dict(row) if row is not None else None


def state_owner(session, model, values):
    if model is Portfolio:
        return values['user_id']
    pid = values['source_portfolio_id'] if model is PortfolioTransfer else values['portfolio_id']
    table = Portfolio.__table__
    return session.connection().execute(db.select(table.c.user_id).where(table.c.id == pid)).scalar_one()


@dataclass(frozen=True)
class AuditRevision:
    id: int
    user_id: int
    mutation_receipt_id: int
    entity_type: str
    entity_id: int
    action: str
    before_state: Optional[str]
    after_state: Optional[str]
    created_at: datetime


class FinancialAuditRepository:
    """No CRUD inheritance: readers cannot add, edit or delete audit records."""

    def __init__(self, user_id):
        self.user_id = user_id

    def _query(self):
        return FinancialAudit.query.filter(
            FinancialAudit.user_id == self.user_id if self.user_id is not None else db.false())

    @staticmethod
    def _view(row):
        return AuditRevision(**{name: getattr(row, name) for name in AuditRevision.__dataclass_fields__})

    def get_by_id(self, identifier):
        row = self._query().filter_by(id=identifier).first()
        return self._view(row) if row else None

    def history(self, *, entity_type=None, entity_id=None, mutation_receipt_id=None, limit=100, offset=0):
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('Invalid audit history page.')
        query = self._query()
        for name, value in (('entity_type', entity_type), ('entity_id', entity_id),
                            ('mutation_receipt_id', mutation_receipt_id)):
            if value is not None:
                query = query.filter(getattr(FinancialAudit, name) == value)
        rows = query.order_by(FinancialAudit.created_at, FinancialAudit.id).offset(offset).limit(limit).all()
        return tuple(self._view(row) for row in rows)

    def _append(self, **values):
        if 'financial_mutation' not in db.session.info:
            raise RuntimeError('Audit append requires the financial mutation owner.')
        db.session.add(FinancialAudit(user_id=self.user_id, **values))
