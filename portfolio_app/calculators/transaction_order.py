"""Canonical accounting order, independent of database and display ordering."""

from datetime import date


# A proposed insert follows persisted peers on the same date and of the same
# type, matching its eventual auto-incremented ID. Edits retain their own ID.
PENDING_TRANSACTION_ID = 2**63


def transaction_order_key(effective_date, transaction_type, transaction_id):
    """Calendar day, Buy before Sell, then ID; preserve legacy null-date order.

    Effective dates are stored wall-clock datetimes. Do not normalize timezones
    or use time of day here: those would change the approved accounting policy.
    """
    day = effective_date.date() if effective_date is not None else date.min
    return (
        effective_date is not None,
        day,
        0 if transaction_type == 'Buy' else 1,
        transaction_id if transaction_id is not None else PENDING_TRANSACTION_ID,
    )


def order_transactions(transactions):
    """Return an accounting-ordered copy of dated, identified trade records.

    Never reorder the caller's list: it may also be used for presentation.
    """
    return sorted(transactions, key=lambda row: transaction_order_key(
        row.date, row.transaction_type, row.id,
    ))
