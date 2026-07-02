from decimal import Decimal
from types import SimpleNamespace

from portfolio_app.calculators.financial_math import (
    calculate_cash_balance,
    calculate_portfolio_metrics,
    calculate_quantity_held,
    calculate_return,
    calculate_symbol_transaction_summary,
)


def _dec(value):
    return Decimal(str(value))


def _tx(transaction_type, price, quantity, fees='0'):
    return SimpleNamespace(
        transaction_type=transaction_type,
        price=_dec(price),
        quantity=_dec(quantity),
        fees=_dec(fees),
    )


def _assert_decimal(value, expected):
    assert isinstance(value, Decimal)
    assert value == _dec(expected)


def _assert_metric_decimals(result):
    for key in ('book_value', 'return_amount', 'return_percent'):
        assert isinstance(result[key], Decimal)


def test_single_buy_includes_fees_in_cost_basis_and_average_cost():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '10', '3', '0.75'),
    ])

    _assert_decimal(summary['total_buy_cost'], '30.75')
    _assert_decimal(summary['total_buy_fees'], '0.75')
    _assert_decimal(summary['cost_basis'], '30.75')
    _assert_decimal(summary['average_cost'], '10.25')
    _assert_decimal(summary['total_quantity_held'], '3')


def test_multiple_buys_use_weighted_average_cost():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
    ])

    _assert_decimal(summary['total_buy_cost'], '58.5')
    _assert_decimal(summary['total_buy_quantity'], '5')
    _assert_decimal(summary['cost_basis'], '58.5')
    _assert_decimal(summary['average_cost'], '11.7')


def test_partial_sell_uses_average_cost_and_sell_fees():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
        _tx('Sell', '15', '2', '1'),
    ])

    _assert_decimal(summary['realized_pnl'], '5.6')
    _assert_decimal(summary['realized_cost_basis'], '23.4')
    _assert_decimal(summary['realized_proceeds'], '29')
    _assert_decimal(summary['total_sell_cost'], '29')
    _assert_decimal(summary['cost_basis'], '35.1')
    _assert_decimal(summary['average_cost'], '11.7')
    _assert_decimal(summary['total_quantity_held'], '3')


def test_full_liquidation_zeroes_open_position_values():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '25', '4', '4'),
        _tx('Sell', '30', '4', '2'),
    ])

    _assert_decimal(summary['total_quantity_held'], '0')
    _assert_decimal(summary['cost_basis'], '0')
    _assert_decimal(summary['average_cost'], '0')
    _assert_decimal(summary['realized_cost_basis'], '104')
    _assert_decimal(summary['realized_proceeds'], '118')
    _assert_decimal(summary['realized_pnl'], '14')


def test_accumulated_realized_pnl_across_multiple_sells():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '10', '10'),
        _tx('Sell', '12', '4', '1'),
        _tx('Buy', '13', '4', '2'),
        _tx('Sell', '11', '5', '0.5'),
    ])

    _assert_decimal(summary['realized_pnl'], '4.5')
    _assert_decimal(summary['realized_cost_basis'], '97')
    _assert_decimal(summary['realized_proceeds'], '101.5')
    _assert_decimal(summary['cost_basis'], '57')
    _assert_decimal(summary['average_cost'], '11.4')


def test_exact_decimal_precision_without_float_conversion():
    summary = calculate_symbol_transaction_summary([
        _tx('Buy', '0.10', '0.10', '0.01'),
        _tx('Buy', '0.30', '0.10', '0.01'),
        _tx('Sell', '0.50', '0.10', '0.002'),
    ])

    for key, value in summary.items():
        if key != 'transaction_count':
            assert isinstance(value, Decimal)

    _assert_decimal(summary['total_buy_cost'], '0.0600')
    _assert_decimal(summary['realized_pnl'], '0.0180')
    _assert_decimal(summary['cost_basis'], '0.0300')
    _assert_decimal(summary['average_cost'], '0.3000')


def test_positive_return_display():
    result = calculate_return(_dec('25'), _dec('0'), _dec('500'))

    _assert_decimal(result['return_amount'], '25')
    _assert_decimal(result['return_percent'], '5.00')
    assert result['return_display'] == '+5.00%'


def test_negative_return_display():
    result = calculate_return(_dec('-11'), _dec('0'), _dec('100'))

    _assert_decimal(result['return_amount'], '-11')
    _assert_decimal(result['return_percent'], '-11.00')
    assert result['return_display'] == '-11.00%'


def test_return_includes_income():
    result = calculate_return(_dec('36'), _dec('25'), _dec('1500'))

    _assert_decimal(result['return_amount'], '61')
    assert result['return_percent'] == _dec('61') / _dec('1500') * _dec('100')
    assert result['return_display'] == '+4.07%'


def test_zero_denominator_return_display():
    result = calculate_return(_dec('0'), _dec('12.34'), _dec('0'))

    _assert_decimal(result['return_amount'], '12.34')
    _assert_decimal(result['return_percent'], '0')
    assert result['return_display'] == '—'


def test_cash_balance_capital_with_no_transactions_or_income():
    cash = calculate_cash_balance(_dec('1000'), [], _dec('0'))

    _assert_decimal(cash, '1000')


def test_cash_balance_subtracts_buy_outflow_including_fees():
    cash = calculate_cash_balance(_dec('1000'), [
        _tx('Buy', '100', '3', '2.5'),
    ], _dec('0'))

    _assert_decimal(cash, '697.5')


def test_cash_balance_adds_sell_proceeds_after_fees():
    cash = calculate_cash_balance(_dec('1000'), [
        _tx('Sell', '120', '2', '3'),
    ], _dec('0'))

    _assert_decimal(cash, '1237')


def test_cash_balance_handles_multiple_buy_sell_records():
    cash = calculate_cash_balance(_dec('2000'), [
        _tx('Buy', '50', '10', '5'),
        _tx('Sell', '60', '4', '2'),
        _tx('Buy', '20', '3', '1'),
    ], _dec('0'))

    _assert_decimal(cash, '1672')


def test_cash_balance_income_increases_cash():
    cash = calculate_cash_balance(_dec('1000'), [], _dec('25.75'))

    _assert_decimal(cash, '1025.75')


def test_cash_balance_combines_capital_transactions_and_income():
    cash = calculate_cash_balance(_dec('1300'), [
        _tx('Buy', '50', '10', '5'),
        _tx('Sell', '60', '4', '2'),
    ], _dec('25'))

    _assert_decimal(cash, '1058')


def test_cash_balance_exact_decimal_precision_without_float_conversion():
    cash = calculate_cash_balance(_dec('1.00'), [
        _tx('Buy', '0.10', '0.10', '0.01'),
        _tx('Sell', '0.30', '0.10', '0.002'),
    ], _dec('0.003'))

    _assert_decimal(cash, '1.011')


def test_cash_balance_zero_values():
    cash = calculate_cash_balance(_dec('0'), [
        _tx('Buy', '0', '0', '0'),
        _tx('Sell', '0', '0', '0'),
    ], _dec('0'))

    _assert_decimal(cash, '0')


def test_quantity_held_empty_transaction_list():
    quantity = calculate_quantity_held([])

    _assert_decimal(quantity, '0')


def test_quantity_held_single_buy():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '3.5'),
    ])

    _assert_decimal(quantity, '3.5')


def test_quantity_held_multiple_buys():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '1.25'),
        _tx('Buy', '0', '2.75'),
    ])

    _assert_decimal(quantity, '4.00')


def test_quantity_held_buy_and_partial_sell():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '10'),
        _tx('Sell', '0', '3.25'),
    ])

    _assert_decimal(quantity, '6.75')


def test_quantity_held_multiple_buy_sell_records():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '10'),
        _tx('Sell', '0', '4'),
        _tx('Buy', '0', '2.5'),
        _tx('Sell', '0', '1.25'),
    ])

    _assert_decimal(quantity, '7.25')


def test_quantity_held_full_liquidation_returns_zero():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '4.0000'),
        _tx('Sell', '0', '4.0000'),
    ])

    _assert_decimal(quantity, '0.0000')


def test_quantity_held_exact_decimal_precision_without_float_conversion():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '0.10'),
        _tx('Buy', '0', '0.20'),
        _tx('Sell', '0', '0.03'),
    ])

    _assert_decimal(quantity, '0.27')


def test_quantity_held_unsupported_transaction_type_is_ignored():
    quantity = calculate_quantity_held([
        _tx('Buy', '0', '5'),
        _tx('Dividend', '0', '99'),
        _tx('Sell', '0', '2'),
    ])

    _assert_decimal(quantity, '3')


def test_portfolio_metrics_cash_plus_positions_produces_book_value():
    result = calculate_portfolio_metrics('1000', '250.5', '0', '0', '1000')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1250.5')
    _assert_decimal(result['return_amount'], '0')
    assert result['return_display'] == '+0.00%'


def test_portfolio_metrics_positive_realized_return():
    result = calculate_portfolio_metrics('1000', '500', '75', '0', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1500')
    _assert_decimal(result['return_amount'], '75')
    _assert_decimal(result['return_percent'], '5.00')
    assert result['return_display'] == '+5.00%'


def test_portfolio_metrics_negative_realized_return():
    result = calculate_portfolio_metrics('1000', '500', '-30', '0', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1500')
    _assert_decimal(result['return_amount'], '-30')
    _assert_decimal(result['return_percent'], '-2.00')
    assert result['return_display'] == '-2.00%'


def test_portfolio_metrics_income_contributes_to_return_amount():
    result = calculate_portfolio_metrics('1000', '500', '0', '45', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['return_amount'], '45')
    _assert_decimal(result['return_percent'], '3.00')
    assert result['return_display'] == '+3.00%'


def test_portfolio_metrics_combines_realized_pnl_and_income():
    result = calculate_portfolio_metrics('1058', '303', '36', '25', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1361')
    _assert_decimal(result['return_amount'], '61')
    assert result['return_percent'] == _dec('61') / _dec('1500') * _dec('100')
    assert result['return_display'] == '+4.07%'


def test_portfolio_metrics_zero_return_denominator_displays_dash():
    result = calculate_portfolio_metrics('100', '50', '10', '5', '0')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '150')
    _assert_decimal(result['return_amount'], '15')
    _assert_decimal(result['return_percent'], '0')
    assert result['return_display'] == '—'


def test_portfolio_metrics_negative_denominator_uses_abs_base():
    result = calculate_portfolio_metrics('100', '50', '10', '5', '-300')

    _assert_metric_decimals(result)
    _assert_decimal(result['return_amount'], '15')
    _assert_decimal(result['return_percent'], '5.00')
    assert result['return_display'] == '+5.00%'


def test_portfolio_metrics_exact_decimal_precision_without_float_conversion():
    result = calculate_portfolio_metrics('0.10', '0.20', '0.03', '0.04', '0.70')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '0.30')
    _assert_decimal(result['return_amount'], '0.07')
    _assert_decimal(result['return_percent'], '10.0')
    assert result['return_display'] == '+10.00%'


def test_portfolio_metrics_all_zero_values():
    result = calculate_portfolio_metrics('0', '0', '0', '0', '0')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '0')
    _assert_decimal(result['return_amount'], '0')
    _assert_decimal(result['return_percent'], '0')
    assert result['return_display'] == '—'
