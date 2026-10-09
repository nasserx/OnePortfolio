"""Exact reconciliation assertions for finite-decimal accounting examples.

These identities describe the current cost-based model, including finite
components derived from recurring averages. They deliberately do not require
nonnegative cash or choose a return denominator. Assertions must not introduce
ambient-context rounding while checking the engine's higher-precision values.
"""

from decimal import Context, Decimal, ROUND_HALF_EVEN
from portfolio_app.utils.financial_arithmetic import exact_add, exact_subtract, exact_sum


def expected_ratio(numerator, denominator, precision=56):
    """Independent reference for the documented minimum division budget."""
    return Context(prec=precision, rounding=ROUND_HALF_EVEN).divide(
        Decimal(numerator), Decimal(denominator),
    )


def expected_percent(numerator, denominator, precision=56):
    ratio = expected_ratio(numerator, denominator, precision)
    return Context(prec=precision + 2, rounding=ROUND_HALF_EVEN).multiply(ratio, Decimal('100'))


def transaction_projection(transaction):
    """Test convenience only; production consumers reuse a batch snapshot."""
    from portfolio_app.calculators import PortfolioCalculator
    return PortfolioCalculator.get_asset_snapshot(
        transaction.portfolio_id, transaction.symbol,
    ).transaction_projections[transaction.id]


def assert_accounting_invariants(summary, *, cash, net_funding, dividend_income, book_value,
                                net_internal_transfers=Decimal('0')):
    values = [cash, net_funding, dividend_income, book_value]
    values.extend(summary[key] for key in (
        'total_purchase_cost', 'net_sale_proceeds', 'position_cost_basis',
        'released_cost_basis', 'realized_trading_pnl', 'total_quantity_held',
        'total_buy_quantity', 'total_sell_quantity',
    ))
    assert all(isinstance(value, Decimal) for value in values)
    assert cash == exact_sum((net_funding, summary['total_purchase_cost'].copy_negate(),
                              summary['net_sale_proceeds'], dividend_income, net_internal_transfers))
    assert book_value == exact_add(cash, summary['position_cost_basis'])
    assert book_value == exact_sum((net_funding, net_internal_transfers, summary['realized_trading_pnl'], dividend_income))
    assert summary['total_quantity_held'] == exact_subtract(
        summary['total_buy_quantity'], summary['total_sell_quantity'])
    assert summary['total_purchase_cost'] == exact_add(summary['position_cost_basis'], summary['released_cost_basis'])
    assert summary['net_sale_proceeds'] == exact_add(summary['released_cost_basis'], summary['realized_trading_pnl'])
