from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from types import SimpleNamespace

from portfolio_app.calculators.financial_math import (
    calculate_cash_balance,
    calculate_portfolio_metrics,
    calculate_quantity_held,
    calculate_realized_earnings_metrics,
    replay_symbol_transactions,
)
from tests._financial import assert_accounting_invariants, expected_percent


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
    for key in ('book_value', 'total_realized_earnings'):
        assert isinstance(result[key], Decimal)
    _assert_return_decimals(result)


def _assert_return_decimals(result):
    for key in ('total_realized_earnings', 'realized_trading_pnl', 'released_cost_basis', 'dividend_income'):
        assert isinstance(result[key], Decimal)
    assert result['realized_trading_return'] is None or isinstance(result['realized_trading_return'], Decimal)


def test_single_buy_includes_fees_in_cost_basis_and_average_cost():
    summary = replay_symbol_transactions([
        _tx('Buy', '10', '3', '0.75'),
    ]).summary

    _assert_decimal(summary['total_purchase_cost'], '30.75')
    _assert_decimal(summary['total_buy_fees'], '0.75')
    _assert_decimal(summary['position_cost_basis'], '30.75')
    _assert_decimal(summary['average_unit_cost'], '10.25')
    _assert_decimal(summary['total_quantity_held'], '3')


def test_multiple_buys_use_weighted_average_cost():
    summary = replay_symbol_transactions([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
    ]).summary

    _assert_decimal(summary['total_purchase_cost'], '58.5')
    _assert_decimal(summary['total_buy_quantity'], '5')
    _assert_decimal(summary['position_cost_basis'], '58.5')
    _assert_decimal(summary['average_unit_cost'], '11.7')


def test_partial_sell_uses_average_cost_and_sell_fees():
    summary = replay_symbol_transactions([
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
        _tx('Sell', '15', '2', '1'),
    ]).summary

    _assert_decimal(summary['realized_trading_pnl'], '5.6')
    _assert_decimal(summary['released_cost_basis'], '23.4')
    _assert_decimal(summary['net_sale_proceeds'], '29')
    _assert_decimal(summary['net_sale_proceeds'], '29')
    _assert_decimal(summary['position_cost_basis'], '35.1')
    _assert_decimal(summary['average_unit_cost'], '11.7')
    _assert_decimal(summary['total_quantity_held'], '3')


def test_full_liquidation_zeroes_open_position_values():
    summary = replay_symbol_transactions([
        _tx('Buy', '25', '4', '4'),
        _tx('Sell', '30', '4', '2'),
    ]).summary

    _assert_decimal(summary['total_quantity_held'], '0')
    _assert_decimal(summary['position_cost_basis'], '0')
    _assert_decimal(summary['average_unit_cost'], '0')
    _assert_decimal(summary['released_cost_basis'], '104')
    _assert_decimal(summary['net_sale_proceeds'], '118')
    _assert_decimal(summary['realized_trading_pnl'], '14')


def test_accumulated_realized_pnl_across_multiple_sells():
    summary = replay_symbol_transactions([
        _tx('Buy', '10', '10'),
        _tx('Sell', '12', '4', '1'),
        _tx('Buy', '13', '4', '2'),
        _tx('Sell', '11', '5', '0.5'),
    ]).summary

    _assert_decimal(summary['realized_trading_pnl'], '4.5')
    _assert_decimal(summary['released_cost_basis'], '97')
    _assert_decimal(summary['net_sale_proceeds'], '101.5')
    _assert_decimal(summary['position_cost_basis'], '57')
    _assert_decimal(summary['average_unit_cost'], '11.4')


def test_exact_decimal_precision_without_float_conversion():
    summary = replay_symbol_transactions([
        _tx('Buy', '0.10', '0.10', '0.01'),
        _tx('Buy', '0.30', '0.10', '0.01'),
        _tx('Sell', '0.50', '0.10', '0.002'),
    ]).summary

    for key, value in summary.items():
        if key != 'transaction_count':
            assert isinstance(value, Decimal)

    _assert_decimal(summary['total_purchase_cost'], '0.0600')
    _assert_decimal(summary['realized_trading_pnl'], '0.0180')
    _assert_decimal(summary['position_cost_basis'], '0.0300')
    _assert_decimal(summary['average_unit_cost'], '0.3000')


def test_positive_trading_return_display():
    result = calculate_realized_earnings_metrics(_dec('25'), _dec('0'), _dec('500'))

    _assert_decimal(result['total_realized_earnings'], '25')
    _assert_decimal(result['realized_trading_return'], '5.00')
    assert result['trading_return_display'] == '+5.00%'


def test_negative_trading_return_display():
    result = calculate_realized_earnings_metrics(_dec('-11'), _dec('0'), _dec('100'))

    _assert_decimal(result['total_realized_earnings'], '-11')
    _assert_decimal(result['realized_trading_return'], '-11.00')
    assert result['trading_return_display'] == '-11.00%'


def test_earnings_include_dividends_but_trading_return_excludes_them():
    result = calculate_realized_earnings_metrics(_dec('36'), _dec('25'), _dec('1500'))

    _assert_decimal(result['total_realized_earnings'], '61')
    assert result['realized_trading_return'] == expected_percent('36', '1500')
    assert result['trading_return_display'] == '+2.40%'


def test_zero_released_basis_trading_return_display():
    result = calculate_realized_earnings_metrics(_dec('0'), _dec('12.34'), _dec('0'))

    _assert_decimal(result['total_realized_earnings'], '12.34')
    assert result['realized_trading_return'] is None
    assert result['trading_return_display'] == '—'


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
    _assert_decimal(result['total_realized_earnings'], '0')
    assert result['trading_return_display'] == '+0.00%'


def test_portfolio_metrics_positive_realized_return():
    result = calculate_portfolio_metrics('1000', '500', '75', '0', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1500')
    _assert_decimal(result['total_realized_earnings'], '75')
    _assert_decimal(result['realized_trading_return'], '5.00')
    assert result['trading_return_display'] == '+5.00%'


def test_portfolio_metrics_negative_realized_return():
    result = calculate_portfolio_metrics('1000', '500', '-30', '0', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1500')
    _assert_decimal(result['total_realized_earnings'], '-30')
    _assert_decimal(result['realized_trading_return'], '-2.00')
    assert result['trading_return_display'] == '-2.00%'


def test_portfolio_metrics_income_contributes_to_total_realized_earnings():
    result = calculate_portfolio_metrics('1000', '500', '0', '45', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '45')
    _assert_decimal(result['realized_trading_return'], '0')
    assert result['trading_return_display'] == '+0.00%'


def test_portfolio_metrics_combines_realized_pnl_and_income():
    result = calculate_portfolio_metrics('1058', '303', '36', '25', '1500')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '1361')
    _assert_decimal(result['total_realized_earnings'], '61')
    assert result['realized_trading_return'] == expected_percent('36', '1500')
    assert result['trading_return_display'] == '+2.40%'


def test_portfolio_metrics_zero_return_denominator_displays_dash():
    result = calculate_portfolio_metrics('100', '50', '10', '5', '0')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '150')
    _assert_decimal(result['total_realized_earnings'], '15')
    assert result['realized_trading_return'] is None
    assert result['trading_return_display'] == '—'


def test_portfolio_metrics_does_not_disguise_invalid_negative_released_basis_with_abs():
    result = calculate_portfolio_metrics('100', '50', '10', '5', '-300')

    _assert_metric_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '15')
    assert result['realized_trading_return'] == expected_percent('10', '-300')
    assert result['trading_return_display'] == '-3.33%'


def test_portfolio_metrics_exact_decimal_precision_without_float_conversion():
    result = calculate_portfolio_metrics('0.10', '0.20', '0.03', '0.04', '0.70')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '0.30')
    _assert_decimal(result['total_realized_earnings'], '0.07')
    assert result['realized_trading_return'] == expected_percent('0.03', '0.70')
    assert result['trading_return_display'] == '+4.29%'


def test_portfolio_metrics_all_zero_values():
    result = calculate_portfolio_metrics('0', '0', '0', '0', '0')

    _assert_metric_decimals(result)
    _assert_decimal(result['book_value'], '0')
    _assert_decimal(result['total_realized_earnings'], '0')
    assert result['realized_trading_return'] is None
    assert result['trading_return_display'] == '—'


def test_trading_earnings_positive_realized_pnl():
    result = calculate_realized_earnings_metrics('50', '0', '1000')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '50')
    _assert_decimal(result['realized_trading_return'], '5.00')
    assert result['trading_return_display'] == '+5.00%'


def test_trading_earnings_negative_realized_pnl():
    result = calculate_realized_earnings_metrics('-25', '0', '500')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '-25')
    _assert_decimal(result['realized_trading_return'], '-5.00')
    assert result['trading_return_display'] == '-5.00%'


def test_trading_earnings_income_contributes_to_total_realized_earnings():
    result = calculate_realized_earnings_metrics('0', '30', '600')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '30')
    _assert_decimal(result['realized_trading_return'], '0')
    assert result['trading_return_display'] == '+0.00%'


def test_trading_earnings_combines_realized_pnl_and_income():
    result = calculate_realized_earnings_metrics('36', '25', '505')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '61')
    assert result['realized_trading_return'] == expected_percent('36', '505')
    assert result['trading_return_display'] == '+7.13%'


def test_trading_earnings_zero_released_basis_displays_dash():
    result = calculate_realized_earnings_metrics('0', '12.34', '0')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '12.34')
    assert result['realized_trading_return'] is None
    assert result['trading_return_display'] == '—'


def test_trading_earnings_does_not_disguise_invalid_negative_released_basis_with_abs():
    result = calculate_realized_earnings_metrics('10', '5', '-300')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '15')
    assert result['realized_trading_return'] == expected_percent('10', '-300')
    assert result['trading_return_display'] == '-3.33%'


def test_trading_earnings_exact_decimal_precision_without_float_conversion():
    result = calculate_realized_earnings_metrics('0.03', '0.04', '0.70')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '0.07')
    assert result['realized_trading_return'] == expected_percent('0.03', '0.70')
    assert result['trading_return_display'] == '+4.29%'


def test_trading_earnings_all_zero_values():
    result = calculate_realized_earnings_metrics('0', '0', '0')

    _assert_return_decimals(result)
    _assert_decimal(result['total_realized_earnings'], '0')
    assert result['realized_trading_return'] is None
    assert result['trading_return_display'] == '—'


def test_remaining_cost_pool_and_invariants_through_liquidation_and_rebuy():
    transactions = [
        _tx('Buy', '10', '2', '1'),
        _tx('Buy', '12', '3', '1.5'),
        _tx('Sell', '15', '2', '1'),
        _tx('Buy', '20', '1'),
        _tx('Sell', '16', '4', '1'),
        _tx('Buy', '7', '2', '2'),
    ]
    # Quantity, remaining basis, unit cost, cumulative trading P&L.
    expected = [
        ('2', '21', '10.5', '0'),
        ('5', '58.5', '11.7', '0'),
        ('3', '35.1', '11.7', '5.6'),
        ('4', '55.1', '13.775', '5.6'),
        ('0', '0', '0', '13.5'),
        ('2', '16', '8', '13.5'),
    ]
    funding, dividend_income = _dec('100'), _dec('2.5')
    for end, state in enumerate(expected, start=1):
        prefix = transactions[:end]
        summary = replay_symbol_transactions(prefix).summary
        assert tuple(summary[key] for key in (
            'total_quantity_held', 'position_cost_basis', 'average_unit_cost', 'realized_trading_pnl',
        )) == tuple(map(_dec, state)), f'after entry {end}'
        cash = calculate_cash_balance(funding, prefix, dividend_income)
        metrics = calculate_portfolio_metrics(
            cash, summary['position_cost_basis'], summary['realized_trading_pnl'], dividend_income, funding,
        )
        assert_accounting_invariants(
            summary, cash=cash, net_funding=funding, dividend_income=dividend_income,
            book_value=metrics['book_value'],
        )
    # Reopening uses only the new purchase pool; lifetime spend is not reset.
    assert summary['total_purchase_cost'] == _dec('94.5')
    assert summary['released_cost_basis'] == _dec('78.5')


def test_repeating_average_full_liquidation_releases_exact_remaining_pool():
    """Phase 4 closes the 5/3 pool exactly, without an epsilon tolerance."""
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        summary = replay_symbol_transactions([
            _tx('Buy', '1', '1'),
            _tx('Buy', '2', '2'),
            _tx('Sell', '3', '3'),
        ]).summary
    assert summary['total_quantity_held'] == _dec('0')
    assert summary['average_unit_cost'] == _dec('0')
    assert summary['position_cost_basis'] == _dec('0')
    assert summary['released_cost_basis'] == _dec('5')
    assert summary['realized_trading_pnl'] == _dec('4')


def test_pure_calculators_preserve_products_beyond_database_decimal_scale():
    """Pure math retains digits that a Numeric(20,10) field cannot represent."""
    transactions = [_tx('Buy', '0.1234567891', '0.0000000001', '0.00000000001')]
    summary = replay_symbol_transactions(transactions).summary
    assert summary['total_quantity_held'] == _dec('0.0000000001')
    assert summary['position_cost_basis'] == _dec('0.00000000002234567891')
    assert summary['average_unit_cost'] == _dec('0.2234567891')
    cash = calculate_cash_balance(_dec('1'), transactions, _dec('0'))
    assert cash == _dec('0.99999999997765432109')
    metrics = calculate_portfolio_metrics(cash, summary['position_cost_basis'], 0, 0, 1)
    assert_accounting_invariants(
        summary, cash=cash, net_funding=_dec('1'), dividend_income=_dec('0'),
        book_value=metrics['book_value'],
    )
