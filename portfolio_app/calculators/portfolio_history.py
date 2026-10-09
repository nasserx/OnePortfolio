"""Presentation projections of linked transfers, never synthetic funding rows."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class TransferEntry:
    id: int
    date: datetime
    event_type: str
    amount_delta: Decimal
    notes: str
    counterparty: str
    transfer: dict

    @property
    def date_short(self):
        return self.date.strftime('%Y-%m-%d')


def build_portfolio_entries(portfolio_id, funding_entries, transfers, portfolio_names):
    entries = list(funding_entries)
    for row in transfers:
        outgoing = row.source_portfolio_id == portfolio_id
        if not outgoing and row.destination_portfolio_id != portfolio_id:
            continue
        other = row.destination_portfolio_id if outgoing else row.source_portfolio_id
        entries.append(TransferEntry(
            row.id, row.date, 'Transfer Out' if outgoing else 'Transfer In',
            row.amount.copy_negate() if outgoing else row.amount, row.notes or '',
            ('To ' if outgoing else 'From ') + portfolio_names.get(other, ''), row.to_dict(),
        ))
    return sorted(entries, key=lambda row: (row.date or datetime.min, row.id))
