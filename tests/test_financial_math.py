from decimal import Decimal
from types import SimpleNamespace

from portfolio_app.calculators.financial_math import (
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
