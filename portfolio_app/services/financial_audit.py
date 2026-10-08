"""Capture server-side persisted facts and append once at the outer boundary."""

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from portfolio_app.models import User
from portfolio_app.models.financial_audit import FinancialAudit
from portfolio_app.repositories.financial_audit_repository import (
    AUDITED_FIELDS, FinancialAuditRepository, persisted_state, state_owner,
)
from portfolio_app.utils.exact_decimal import canonical_decimal_text


def canonical_snapshot(values):
    if values is None:
        return None
    def encode(value):
        if isinstance(value, Decimal):
            return canonical_decimal_text(value)
        if isinstance(value, datetime):
            # Database DateTime columns are naive. Preserve their stored wall
            # time, including microseconds, without inventing execution time.
            return value.isoformat(timespec='microseconds')
        if value is None or isinstance(value, (str, int, bool)):
            return value
        raise TypeError('Unsupported financial audit value')
    return json.dumps({key: encode(value) for key, value in values.items()},
                      sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


@event.listens_for(Session, 'before_flush')
def capture_financial_changes(session, flush_context, instances):
    for row in session.dirty.union(session.deleted):
        if isinstance(row, FinancialAudit):
            raise RuntimeError('Financial audit records are append-only.')
    state = session.info.get('financial_mutation')
    if state is None:
        return  # Raw test/legacy imports outside application services are not audited.
    captured = state.setdefault('audit_changes', {})
    for row in list(session.new) + list(session.dirty) + list(session.deleted):
        model = type(row)
        if model not in AUDITED_FIELDS or row in captured:
            continue
        before = None if row in session.new else persisted_state(session, model, row.id)
        values = before if before is not None else {name: getattr(row, name) for name in AUDITED_FIELDS[model]}
        owner = state_owner(session, model, values)
        captured[row] = (owner, before)
        state['users'].add(owner)


def append_financial_audit(session, state):
    """Called after final financial/receipt flush, before the owner's commit."""
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    for row, (owner, before) in state.get('audit_changes', {}).items():
        if session.get(User, owner) is None:
            continue  # Account deletion removes the account's entire history.
        after = None if inspect(row).deleted else persisted_state(session, type(row), row.id)
        # Automatic update timestamps alone do not invent a domain revision.
        meaningful = lambda values: None if values is None else {
            key: value for key, value in values.items() if key != 'updated_at'
        }
        if canonical_snapshot(meaningful(before)) == canonical_snapshot(meaningful(after)):
            continue
        receipt = state['receipts'][owner]
        if receipt.user_id != owner or receipt.id is None:
            raise RuntimeError('Audit mutation receipt is missing or belongs to another account.')
        FinancialAuditRepository(owner)._append(
            mutation_receipt_id=receipt.id, entity_type=type(row).__tablename__, entity_id=row.id,
            action='create' if before is None else 'delete' if after is None else 'update',
            before_state=canonical_snapshot(before), after_state=canonical_snapshot(after), created_at=timestamp,
        )
