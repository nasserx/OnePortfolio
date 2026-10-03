"""Exact reconciliation assertions for finite-decimal accounting examples.

These identities describe the current cost-based model. They deliberately do
not require nonnegative cash or choose a return denominator. Repeating-average
rounding residuals are characterized separately, without weakening these checks.
"""

from decimal import Decimal


def assert_accounting_invariants(summary, *, cash, net_funding, income, book_value):
    values = [cash, net_funding, income, book_value]
    values.extend(summary[key] for key in (
        'total_buy_cost', 'realized_proceeds', 'cost_basis',
        'realized_cost_basis', 'realized_pnl', 'total_quantity_held',
        'total_buy_quantity', 'total_sell_quantity',
    ))
    assert all(isinstance(value, Decimal) for value in values)
    assert cash == (
        net_funding - summary['total_buy_cost']
        + summary['realized_proceeds'] + income
    )
    assert book_value == cash + summary['cost_basis']
    assert book_value == net_funding + summary['realized_pnl'] + income
    assert summary['total_quantity_held'] == (
        summary['total_buy_quantity'] - summary['total_sell_quantity']
    )
    assert summary['total_buy_cost'] == (
        summary['cost_basis'] + summary['realized_cost_basis']
    )
    assert summary['realized_proceeds'] == (
        summary['realized_cost_basis'] + summary['realized_pnl']
    )
