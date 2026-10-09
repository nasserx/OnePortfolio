"""Canonical accounting order is independent of retrieval/presentation order."""

from datetime import datetime
from decimal import Decimal
from itertools import permutations
from types import SimpleNamespace

from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.calculators.transaction_order import order_transactions, transaction_order_key


def _row(identifier, kind, day, hour, price):
    return SimpleNamespace(
        id=identifier, transaction_type=kind, date=datetime(2024, 1, day, hour),
        price=Decimal(price), quantity=Decimal('1'), fees=Decimal('0'),
    )


def test_all_retrieval_permutations_have_identical_accounting_without_mutating_display():
    # IDs, times and types deliberately disagree. IDs order BOTH buy and sell
    # peers; the previous day wins even though its ID is greatest.
    rows = [
        _row(9, 'Buy', 1, 23, '100'),
        _row(3, 'Buy', 2, 20, '200'),
        _row(4, 'Buy', 2, 8, '300'),
        _row(1, 'Sell', 2, 22, '250'),
        _row(2, 'Sell', 2, 1, '150'),
    ]
    for permutation in permutations(rows):
        supplied = list(permutation)
        original_ids = [row.id for row in supplied]
        ordered = order_transactions(supplied)
        assert [row.id for row in ordered] == [9, 3, 4, 1, 2]
        summary = PortfolioCalculator.get_symbol_transactions_summary_from_list(supplied)
        assert summary['total_quantity_held'] == Decimal('1')
        assert summary['position_cost_basis'] == summary['average_unit_cost'] == Decimal('200')
        assert summary['realized_trading_pnl'] == Decimal('0')
        assert summary['released_cost_basis'] == Decimal('400')
        assert [row.id for row in supplied] == original_ids


def test_pending_insert_follows_same_day_same_type_peers_and_edit_retains_id():
    day = datetime(2024, 1, 1)
    assert transaction_order_key(day, 'Buy', 1) < transaction_order_key(day, 'Buy', 2)
    assert transaction_order_key(day, 'Buy', 2) < transaction_order_key(day, 'Buy', None)
    assert transaction_order_key(day, 'Buy', None) < transaction_order_key(day, 'Sell', 1)
    assert transaction_order_key(day, 'Sell', 2) < transaction_order_key(day, 'Sell', None)


def test_legacy_null_effective_date_precedes_all_dated_records():
    assert transaction_order_key(None, 'Sell', 2) < transaction_order_key(datetime.min, 'Buy', 1)
    assert transaction_order_key(None, 'Buy', 3) < transaction_order_key(None, 'Sell', 2)
