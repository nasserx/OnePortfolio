"""Phase 8 policy: only realized trading P&L / released cost basis is a return."""

from datetime import datetime
from decimal import Decimal as D, Inexact, Rounded, ROUND_UP, localcontext
from types import SimpleNamespace

import pytest
from flask import render_template_string

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import (
    calculate_realized_earnings_metrics, calculate_realized_trading_return,
)
from portfolio_app.utils.financial_arithmetic import exact_add, division_precision
from tests._auth import authenticate_client
from tests._financial import assert_accounting_invariants, expected_percent
from tests.test_financial_baseline import ledger, _trade


def _scopes(ledger, symbol='BTC'):
    global_state = PC.get_financial_snapshot(ledger.uid)
    portfolio = next(p for p in global_state.portfolios if p.portfolio_id == ledger.pid)
    asset = portfolio.asset(symbol)
    return asset, portfolio, global_state


def _assert_single_sale_agreement(ledger, sale, expected):
    asset, portfolio, global_state = _scopes(ledger, sale.symbol)
    row = asset.transaction_projections[sale.id]
    assert row.realized_trading_return == row.trade_return_percent == expected
    for metrics in (asset.returns, portfolio.metrics, global_state.totals):
        assert metrics['realized_trading_return'] == metrics['return_percent'] == expected
        assert metrics['released_cost_basis'] == row.released_cost_basis
        assert metrics['realized_trading_pnl'] == row.realized_trading_pnl
    assert_accounting_invariants(portfolio.transactions, cash=portfolio.cash_balance,
        net_funding=portfolio.net_contributions, income=portfolio.dividend_income,
        book_value=portfolio.metrics['book_value'])
    return asset, portfolio, global_state


def test_btc_all_four_scopes_agree_through_principal_profit_withdrawal_and_redeposit(ledger):
    _trade(ledger, 'Buy', '185000', '0.003', 1)
    assert PC.get_available_cash_for_portfolio(ledger.pid) == D('-555')
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('555'))
    sale = _trade(ledger, 'Sell', '186000', '0.003', 3)
    expected = expected_percent('3', '555')
    _assert_single_sale_agreement(ledger, sale, expected)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('555'))
    _assert_single_sale_agreement(ledger, sale, expected)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('3'))
    _assert_single_sale_agreement(ledger, sale, expected)
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('3'))
    asset, portfolio, global_state = _assert_single_sale_agreement(ledger, sale, expected)
    row = asset.transaction_projections[sale.id]
    assert row.net_sale_proceeds == D('558')
    assert row.released_cost_basis == D('555')
    assert (portfolio.cash_balance, portfolio.net_contributions, asset.transactions['total_quantity_held'],
            asset.transactions['cost_basis'], portfolio.metrics['total_realized_earnings'],
            global_state.totals['total_value']) == tuple(map(D, ('3', '0', '0', '0', '3', '3')))


def test_unused_deposit_open_purchase_and_dividend_cannot_dilute_realized_return(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('100'))
    _trade(ledger, 'Buy', '100', '1', 1)
    sale = _trade(ledger, 'Sell', '110', '1', 2)
    _assert_single_sale_agreement(ledger, sale, D('10'))
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _assert_single_sale_agreement(ledger, sale, D('10'))
    _trade(ledger, 'Buy', '1000', '1', 3)
    before = _assert_single_sale_agreement(ledger, sale, D('10'))[1]
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('50'), datetime(2024, 1, 4))
    asset, after, global_state = _assert_single_sale_agreement(ledger, sale, D('10'))
    for metrics in (asset.returns, after.metrics, global_state.totals):
        assert metrics['total_realized_earnings'] == D('60')
        assert metrics['dividend_income'] == D('50')
    assert after.cash_balance == exact_add(before.cash_balance, D('50'))
    assert after.metrics['book_value'] == exact_add(before.metrics['book_value'], D('50'))
    assert before.transactions == after.transactions
    assert asset.transactions['cost_basis'] == D('1000')
    assert after.metrics['released_cost_basis'] == D('100')


@pytest.mark.parametrize('funding,buy,dividend', [
    ('0', False, '100'), ('1000', False, '100'), ('1000', True, '100'),
    ('1000', True, '0'), ('0', False, '0'),
])
def test_no_sale_and_dividend_only_states_have_undefined_return(ledger, funding, buy, dividend):
    if D(funding):
        ledger.svc.portfolio_service.deposit_funds(ledger.pid, D(funding))
    if buy:
        _trade(ledger, 'Buy', '100', '1', 1)
    if D(dividend):
        ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D(dividend), datetime(2024, 1, 2))
    asset, portfolio, global_state = _scopes(ledger)
    for metrics in (asset.returns, portfolio.metrics, global_state.totals):
        assert metrics['released_cost_basis'] == metrics['realized_trading_pnl'] == D('0')
        assert metrics['realized_trading_return'] is metrics['return_percent'] is None
        assert metrics['return_display'] == '—'
        assert metrics['total_realized_earnings'] == D(dividend)


@pytest.mark.parametrize('sale_price,return_value', [('100', '0'), ('110', '10'), ('90', '-10')])
def test_zero_positive_negative_sale_return_at_every_scope(ledger, sale_price, return_value):
    _trade(ledger, 'Buy', '100', '1', 1)
    sale = _trade(ledger, 'Sell', sale_price, '1', 2)
    _assert_single_sale_agreement(ledger, sale, D(return_value))


def test_multiple_sales_aggregate_components_not_percentages(ledger):
    _trade(ledger, 'Buy', '100', '1', 1)
    first = _trade(ledger, 'Sell', '110', '1', 2)
    _trade(ledger, 'Buy', '200', '1', 3)
    second = _trade(ledger, 'Sell', '195', '1', 4)
    asset, portfolio, global_state = _scopes(ledger)
    assert asset.transaction_projections[first.id].realized_trading_return == D('10')
    assert asset.transaction_projections[second.id].realized_trading_return == D('-2.5')
    for metrics in (asset.returns, portfolio.metrics, global_state.totals):
        assert metrics['realized_trading_pnl'] == D('5')
        assert metrics['released_cost_basis'] == D('300')
        assert metrics['realized_trading_return'] == expected_percent('5', '300')
        assert metrics['realized_trading_return'] != D('3.75')


@pytest.mark.parametrize('separate_portfolios', [False, True])
def test_multiple_assets_or_portfolios_sum_pnl_and_basis_before_dividing(ledger, separate_portfolios):
    other = ledger
    if separate_portfolios:
        portfolio = ledger.svc.portfolio_service.create_portfolio('Other', user_id=ledger.uid)
        other = SimpleNamespace(uid=ledger.uid, pid=portfolio.id, svc=ledger.svc)
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    ledger.svc.portfolio_service.deposit_funds(other.pid, D('10000'))
    _trade(ledger, 'Buy', '100', '1', 1, symbol='AAA')
    _trade(ledger, 'Sell', '120', '1', 2, symbol='AAA')
    _trade(other, 'Buy', '200', '1', 1, symbol='BBB')
    _trade(other, 'Sell', '190', '1', 2, symbol='BBB')
    before = PC.get_financial_snapshot(ledger.uid)
    assert before.totals['realized_trading_pnl'] == D('10')
    assert before.totals['released_cost_basis'] == D('300')
    assert before.totals['realized_trading_return'] == expected_percent('10', '300')
    assert before.totals['realized_trading_return'] != D('7.5')
    ledger.svc.portfolio_service.deposit_funds(other.pid, D('90000'))
    after = PC.get_financial_snapshot(ledger.uid)
    assert after.totals['realized_trading_return'] == before.totals['realized_trading_return']
    if not separate_portfolios:
        assert before.portfolios[0].metrics['realized_trading_return'] == before.totals['realized_trading_return']


def test_partial_sale_releases_only_sold_basis_and_fees_are_not_deducted_twice(ledger):
    _trade(ledger, 'Buy', '99', '10', 1, fees='10')
    sale = _trade(ledger, 'Sell', '120', '2.5', 2, fees='5')
    asset, portfolio, _ = _assert_single_sale_agreement(ledger, sale, D('18'))
    assert asset.transactions['cost_basis'] == D('750')
    assert portfolio.metrics['released_cost_basis'] == D('250')
    assert portfolio.metrics['realized_trading_pnl'] == D('45')
    assert asset.transactions['total_buy_cost'] == D('1000')


@pytest.mark.parametrize('precision', [3, 28, 90])
def test_repeating_high_precision_row_and_aggregate_return_share_identical_projection(ledger, precision):
    _trade(ledger, 'Buy', '1234567890.1234567890123456789012345', '1', 1)
    _trade(ledger, 'Buy', '2', '2', 2)
    sale = _trade(ledger, 'Sell', '1234567891.1234567890123456789012345', '1', 3, fees='1E-31')
    db.session.expire_all()
    asset, _, _ = _scopes(ledger)
    row = asset.transaction_projections[sale.id]
    p = division_precision((row.realized_trading_pnl, row.released_cost_basis))
    expected = expected_percent(row.realized_trading_pnl, row.released_cost_basis, precision=p)
    with localcontext() as ambient:
        ambient.prec = precision
        ambient.rounding = ROUND_UP
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        flags = dict(ambient.flags)
        _assert_single_sale_agreement(ledger, sale, expected)
        assert ambient.prec == precision and ambient.flags == flags


@pytest.mark.parametrize('pnl,basis,text,tone', [
    ('0', '0', '—', 'num--flat'), ('0', '100', '0.00%', 'num--flat'),
    ('10', '100', '+10.00%', 'num--pos'), ('-5', '200', '-2.50%', 'num--neg'),
])
def test_existing_percentage_macro_preserves_undefined_zero_signs_and_tones(app, pnl, basis, text, tone):
    with app.test_request_context():
        metrics = calculate_realized_earnings_metrics(pnl, '50', basis)
        html = render_template_string(
            "{% from 'macros/ui.html' import percent %}{{ percent(value, display) }}",
            value=metrics['realized_trading_return'], display=metrics['return_display'])
    assert f'>{text}</span>' in html
    assert tone in html


def test_api_and_overview_expose_new_semantics_without_losing_exact_decimal_strings(ledger, app):
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('50'), datetime(2024, 1, 1))
    payload = client.get('/api/portfolio-summary').get_json()['portfolio_summary'][0]
    assert payload['return_percent'] is payload['realized_trading_return'] is None
    assert D(payload['total_realized_earnings']) == D('50')
    assert 'return_amount' not in payload
    html = client.get('/').get_data(as_text=True)
    assert 'Realized Trading Return' in html
    assert 'Realized Return On Total Capital' not in html
    assert 'delta delta--flat">—</span>' in html
    _trade(ledger, 'Buy', '100', '1', 2)
    _trade(ledger, 'Sell', '100', '1', 3)
    payload = client.get('/api/portfolio-summary').get_json()['portfolio_summary'][0]
    assert isinstance(payload['realized_trading_return'], str)
    assert D(payload['realized_trading_return']) == D('0')
    assert D(payload['dividend_income']) == D('50')
    assert D(payload['released_cost_basis']) == D('100')
    assert D(payload['total_realized_earnings']) == D('50')


def test_obsolete_return_helpers_are_not_available_as_production_fallbacks():
    from portfolio_app.calculators import financial_math
    assert not hasattr(financial_math, 'calculate_return')
    assert not hasattr(financial_math, 'calculate_asset_return')
    assert calculate_realized_trading_return('0', '0') is None
    assert calculate_realized_trading_return('0', '100') == D('0')
