"""Phase 7: exact finite operations, explicit recurring precision, no ambient state."""

from datetime import datetime
from decimal import Context, Decimal as D, Inexact, Rounded, ROUND_UP, localcontext
from fractions import Fraction
from itertools import permutations
from types import SimpleNamespace

import pytest

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import (
    calculate_cash_balance, calculate_portfolio_metrics, calculate_quantity_held,
    calculate_realized_earnings_metrics as calculate_return,
)
from portfolio_app.calculators.financial_snapshots import build_asset_snapshot
from portfolio_app.services.transaction_service import ValidationError
from portfolio_app.utils.financial_arithmetic import (
    FinancialArithmetic, division_precision, exact_add, exact_subtract,
    exact_multiply, exact_sum, financial_divide,
)
from tests._financial import assert_accounting_invariants, expected_ratio, expected_percent
from tests.test_financial_baseline import ledger, _trade


PRICE = D('1234567890.1234567890123456789012345')
QUANTITY = D('1.000000000000000000000000000001')
FEE = D('0.0000000000000000000000000000007')
# Independent test oracle; every finite operation below fits in 400 digits.
# Trap Inexact so expected values cannot silently lose digits either.
REFERENCE = Context(prec=400, traps=[Inexact])


def _row(identifier, kind, price, quantity, fee='0'):
    return SimpleNamespace(id=identifier, portfolio_id=1, symbol='PREC',
                           transaction_type=kind, price=D(price), quantity=D(quantity),
                           fees=D(fee), date=datetime(2024, 1, identifier))


@pytest.mark.parametrize('left,right', [
    (PRICE, QUANTITY), (D('1E80'), D('1E-80')),
    (D('9' * 130), D('0.' + '0' * 120 + '7')),
    (D('-123456789012345678901234567890.001'), D('0.0000000000001')),
])
def test_finite_operations_are_exact_against_independent_rational_oracle(left, right):
    with localcontext() as ambient:
        ambient.prec = 3
        ambient.rounding = ROUND_UP
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        assert Fraction(exact_add(left, right)) == Fraction(left) + Fraction(right)
        assert Fraction(exact_subtract(left, right)) == Fraction(left) - Fraction(right)
        assert Fraction(exact_multiply(left, right)) == Fraction(left) * Fraction(right)
        assert exact_sum((left, right, left.copy_negate())) == right


def test_sum_is_exact_across_large_cancellation_and_retrieval_orders():
    values = (D('1E200'), D('1E-180'), D('-1E200'), D('0.00003'))
    expected = D('0.00003' + '0' * 174 + '1')
    for supplied in permutations(values):
        assert exact_sum(supplied) == expected
    assert exact_sum([]) == D('0')
    assert exact_sum([D('-0E-100'), D('0')]) == D('0')


def test_division_budget_is_explicit_dynamic_and_representation_independent():
    assert division_precision([D('5'), D('3')]) == 56
    # Significant positions span +10 through -25: span 35; 3 values need 1 carry.
    assert division_precision([PRICE, D('1'), D('0')]) == 99
    assert division_precision([PRICE, D('1.0000'), D('-0E-100')]) == 99
    assert division_precision([D('1E100'), D('1E-100')]) == 431
    assert division_precision([D('5'), D('3')]) == division_precision([D('5.000'), D('3.0')])


def test_repeating_division_has_defined_half_even_precision_and_zero_behavior():
    arithmetic = FinancialArithmetic.for_values((D('5'), D('3')))
    assert arithmetic.divide(5, 3) == D('1.' + '6' * 54 + '7')
    assert arithmetic.divide(1, 3) == D('0.' + '3' * 56)
    assert arithmetic.divide(5, 0) == D('0')
    assert arithmetic.divide(5, 0, None) is None
    # The class accepts an explicit budget; ties are half-even, not display HALF_UP.
    assert FinancialArithmetic(2).divide('1.25', '1') == D('1.2')
    assert FinancialArithmetic(2).divide('1.35', '1') == D('1.4')


def test_one_raw_input_division_budget_is_used_for_every_replay_step(monkeypatch):
    rows = [_row(1, 'Buy', '1', '1'), _row(2, 'Buy', '2', '2'),
            _row(3, 'Sell', '3', '1'), _row(4, 'Sell', '3', '2')]
    import portfolio_app.calculators.financial_math as engine
    original = engine.FinancialArithmetic
    budgets = []

    class RecordedArithmetic:
        @staticmethod
        def for_values(values):
            arithmetic = original.for_values(values)
            budgets.append(arithmetic.precision)
            return arithmetic

    monkeypatch.setattr(engine, 'FinancialArithmetic', RecordedArithmetic)
    replay = engine.replay_symbol_transactions(rows)
    assert budgets == [56]
    assert replay.summary['cost_basis'] == D('0')
    assert replay.summary['realized_pnl'] == D('4')


def test_repeating_partial_sales_reconcile_exact_components_through_full_liquidation():
    rows = [_row(1, 'Buy', '1', '1'), _row(2, 'Buy', '2', '2'),
            _row(3, 'Sell', '3', '1'), _row(4, 'Buy', '2', '1'),
            _row(5, 'Sell', '3', '1'), _row(6, 'Sell', '3', '2')]
    for end in range(1, len(rows) + 1):
        snapshot = build_asset_snapshot('PREC', rows[:end])
        summary = snapshot.transactions
        cash = calculate_cash_balance(D('0'), rows[:end], D('0'))
        metrics = calculate_portfolio_metrics(cash, summary['cost_basis'], summary['realized_pnl'], 0, 0)
        assert_accounting_invariants(summary, cash=cash, net_funding=D('0'), income=D('0'),
                                     book_value=metrics['book_value'])
        sales = [r for r in snapshot.transaction_projections.values() if r.transaction_type == 'Sell']
        # Independent rational checks on the finite canonical components.
        assert sum((Fraction(r.realized_trading_pnl) for r in sales), Fraction(0)) == Fraction(summary['realized_pnl'])
        assert sum((Fraction(r.released_cost_basis) for r in sales), Fraction(0)) == Fraction(summary['realized_cost_basis'])
    partial = snapshot.transaction_projections[3]
    assert partial.released_cost_basis == D('1.' + '6' * 54 + '7')
    assert partial.post_cost_basis == D('3.' + '3' * 55)
    assert partial.realized_trading_pnl == D('1.' + '3' * 55)
    assert summary['total_quantity_held'] == summary['cost_basis'] == summary['average_cost'] == D('0')
    assert summary['realized_pnl'] == D('5')


def test_nonzero_tiny_position_is_not_clamped():
    rows = [_row(1, 'Buy', '1', '1.000000000000000000000000000001'),
            _row(2, 'Sell', '1', '1')]
    summary = build_asset_snapshot('PREC', rows).transactions
    assert summary['total_quantity_held'] == summary['cost_basis'] == D('1E-30')
    assert summary['average_cost'] == D('1')


@pytest.mark.parametrize('ambient_precision', [3, 9, 28, 90])
def test_persistence_replay_snapshots_and_validation_ignore_ambient_context(ledger, ambient_precision):
    _trade(ledger, 'Buy', str(PRICE), str(QUANTITY), 1, fees=str(FEE))
    _trade(ledger, 'Buy', '2', '2', 2)
    _trade(ledger, 'Sell', '3', '1', 3, fees=str(FEE))
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('9000000000.00000000000000000000001'))
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', FEE, datetime(2024, 1, 4))
    db.session.expire_all()
    expected = PC.get_financial_snapshot(ledger.uid)
    expected_rows = expected.as_portfolio_summary()
    with localcontext() as ambient:
        ambient.prec = ambient_precision
        ambient.rounding = ROUND_UP
        ambient.Emin, ambient.Emax = -9, 9
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        flags = dict(ambient.flags)
        db.session.expire_all()
        actual = PC.get_financial_snapshot(ledger.uid)
        assert actual == expected
        assert actual.as_portfolio_summary() == expected_rows
        assert PC.get_available_cash_for_portfolio(ledger.pid) == expected.totals['total_cash']
        assert PC.get_quantity_held_for_symbol(ledger.pid, 'BTC') == D('2.000000000000000000000000000001')
        assert ledger.svc.transaction_service._proposed_cash_effect('Buy', PRICE, QUANTITY, FEE) == (
            REFERENCE.add(REFERENCE.multiply(PRICE, QUANTITY), FEE).copy_negate())
        assert ambient.prec == ambient_precision and ambient.rounding == ROUND_UP
        assert (ambient.Emin, ambient.Emax) == (-9, 9)
        assert ambient.flags == flags
        assert ambient.traps[Inexact] and ambient.traps[Rounded]


def test_high_precision_db_to_replay_fees_cash_basis_and_partial_then_full_sale(ledger):
    purchase = REFERENCE.add(REFERENCE.multiply(PRICE, QUANTITY), FEE)
    first = _trade(ledger, 'Buy', str(PRICE), str(QUANTITY), 1, fees=str(FEE))
    db.session.refresh(first)
    assert (first.price, first.quantity, first.fees) == (PRICE, QUANTITY, FEE)
    bought = PC.get_asset_snapshot(ledger.pid, 'BTC')
    projection = bought.transaction_projections[first.id]
    assert projection.gross_amount == REFERENCE.multiply(PRICE, QUANTITY)
    assert projection.purchase_cost == bought.transactions['cost_basis'] == purchase
    assert projection.post_average_unit_cost == expected_ratio(purchase, QUANTITY, precision=111)
    assert PC.get_available_cash_for_portfolio(ledger.pid) == purchase.copy_negate()
    assert purchase != Context(prec=28).add(Context(prec=28).multiply(PRICE, QUANTITY), FEE)

    _trade(ledger, 'Buy', str(PRICE), '2', 2, fees=str(FEE))
    sale_price = D('2234567890.1234567890123456789012345')
    sale = _trade(ledger, 'Sell', str(sale_price), '1', 3, fees=str(FEE))
    partial = PC.get_portfolio_snapshot(ledger.pid)
    row = partial.asset('BTC').transaction_projections[sale.id]
    total_cost = REFERENCE.add(purchase, REFERENCE.add(REFERENCE.multiply(PRICE, D('2')), FEE))
    expected_average = expected_ratio(total_cost, D('3.000000000000000000000000000001'), precision=111)
    assert row.applicable_average_unit_cost == row.released_cost_basis == expected_average
    assert row.net_sale_proceeds == REFERENCE.subtract(sale_price, FEE)
    assert row.realized_trading_pnl == REFERENCE.subtract(row.net_sale_proceeds, row.released_cost_basis)
    # Return is now a shared direct-operand projection, independent of scope.
    from portfolio_app.utils.financial_arithmetic import division_precision
    precision = division_precision((row.realized_trading_pnl, row.released_cost_basis))
    assert row.trade_return_percent == expected_percent(row.realized_trading_pnl, row.released_cost_basis, precision=precision)
    assert_accounting_invariants(partial.transactions, cash=partial.cash_balance,
                                 net_funding=D('0'), income=D('0'), book_value=partial.metrics['book_value'])
    remaining = D('2.000000000000000000000000000001')
    _trade(ledger, 'Sell', str(sale_price), str(remaining), 4, fees=str(FEE))
    closed = PC.get_portfolio_snapshot(ledger.pid)
    assert closed.transactions['total_quantity_held'] == closed.transactions['cost_basis'] == D('0')
    total_quantity = D('3.000000000000000000000000000001')
    expected_profit = REFERENCE.subtract(
        REFERENCE.multiply(D('1000000000'), total_quantity), REFERENCE.multiply(FEE, D('4')))
    assert closed.transactions['realized_pnl'] == closed.cash_balance == expected_profit
    assert_accounting_invariants(closed.transactions, cash=closed.cash_balance,
                                 net_funding=D('0'), income=D('0'), book_value=closed.metrics['book_value'])


def test_high_precision_income_funding_and_multiple_portfolio_aggregation(ledger):
    second = ledger.svc.portfolio_service.create_portfolio('Other', user_id=ledger.uid)
    funding = D('123456789012345678901234567890.123456789012345678901')
    income = D('0.0000000000000000000000000000001')
    for pid in (ledger.pid, second.id):
        ledger.svc.portfolio_service.deposit_funds(pid, funding)
        ledger.svc.portfolio_service.deposit_funds(pid, FEE)
        ledger.svc.transaction_service.add_dividend(pid, 'BTC', income, datetime(2024, 1, 1))
        ledger.svc.transaction_service.add_dividend(pid, 'BTC', income, datetime(2024, 1, 2))
    db.session.expire_all()
    global_state = PC.get_financial_snapshot(ledger.uid)
    expected_funding = REFERENCE.add(funding, FEE)
    expected_income = REFERENCE.multiply(income, D('2'))
    expected_cash = REFERENCE.add(expected_funding, expected_income)
    for portfolio in global_state.portfolios:
        assert portfolio.net_contributions == portfolio.funding_inflows == expected_funding
        assert portfolio.income == expected_income
        assert portfolio.cash_balance == portfolio.metrics['book_value'] == expected_cash
        assert portfolio.withdrawals == D('0')
    assert global_state.totals['total_cash'] == REFERENCE.multiply(expected_cash, D('2'))
    assert global_state.totals['total_capital'] == REFERENCE.multiply(expected_funding, D('2'))
    assert global_state.totals['total_income'] == REFERENCE.multiply(expected_income, D('2'))
    assert global_state.total_book_value == global_state.totals['total_value']


def test_validation_walk_and_fee_limit_retain_tiny_distinctions(ledger):
    quantity = D('1.000000000000000000000000000001')
    with localcontext() as ambient:
        ambient.prec = 3
        _trade(ledger, 'Buy', '1', str(quantity), 1)
        _trade(ledger, 'Sell', '1', '1', 2)
        assert PC.get_quantity_held_for_symbol(ledger.pid, 'BTC') == D('1E-30')
        with pytest.raises(ValidationError):
            _trade(ledger, 'Sell', '1', '2E-30', 3)
        with pytest.raises(ValidationError):
            _trade(ledger, 'Sell', '1', '1E-30', 3, fees='1.000000000000000000000000000001E-30')
        _trade(ledger, 'Sell', '1', '1E-30', 3)
        assert PC.get_quantity_held_for_symbol(ledger.pid, 'BTC') == D('0')


def test_legacy_return_display_is_independent_of_ambient_rounding():
    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_UP
        result = calculate_return('1.005', '0', '100')
        assert result['return_percent'] == D('1.005')
        assert result['return_display'] == '+1.00%'
        assert ambient.rounding == ROUND_UP


def test_standalone_quantity_and_divide_boundaries_are_context_independent():
    rows = [_row(1, 'Buy', '1', str(QUANTITY)), _row(2, 'Sell', '1', '1')]
    with localcontext() as ambient:
        ambient.prec = 2
        assert calculate_quantity_held(rows) == D('1E-30')
        assert financial_divide(D('5'), D('3')) == expected_ratio('5', '3')
