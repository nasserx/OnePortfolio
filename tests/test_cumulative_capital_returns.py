"""Approved cumulative book returns, separate from retained trading metrics."""

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal as D, Inexact, Rounded, localcontext
import re

import pytest
from sqlalchemy import event

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import calculate_cumulative_return
from portfolio_app.models import User, PortfolioEvent
from portfolio_app.services.factory import Services
from portfolio_app.utils.financial_arithmetic import exact_add, exact_subtract, division_precision
from tests._auth import authenticate_client
from tests._financial import assert_accounting_invariants, expected_percent
from tests.test_financial_baseline import ledger


def day(n):
    return datetime(2024, 1, n)


def trade(ledger, kind, price, quantity='1', n=2, fees='0'):
    return ledger.svc.transaction_service.add_transaction(
        ledger.pid, kind, 'BTC', D(price), D(quantity), D(fees), date=day(n),
    )


def state(ledger):
    global_state = PC.get_financial_snapshot(ledger.uid)
    for portfolio in global_state.portfolios:
        assert_accounting_invariants(
            portfolio.transactions, cash=portfolio.cash_balance,
            net_funding=portfolio.net_contributions,
            net_internal_transfers=portfolio.net_internal_transfers,
            dividend_income=portfolio.dividend_income,
            book_value=portfolio.metrics['book_value'],
        )
    assert global_state.totals['total_realized_earnings'] == exact_subtract(
        global_state.totals['book_value'], global_state.totals['net_contributions'],
    )
    return next(p for p in global_state.portfolios if p.portfolio_id == ledger.pid), global_state


@pytest.mark.parametrize('earnings,capital,expected', [
    ('1500', '1000', '150'), ('-150', '1000', '-15'), ('0', '1000', '0'),
    ('50', '0', None), ('0', '0', None), ('-50', '0', None),
])
def test_cumulative_percentage_contract(earnings, capital, expected):
    result = calculate_cumulative_return(earnings, capital)
    assert result == (D(expected) if expected is not None else None)


@pytest.mark.parametrize('earnings,capital', [
    ('1', '-1'), ('NaN', '100'), ('1', 'Infinity'), (0.1, '100'), ('1', 0.1),
])
def test_invalid_capital_or_inexact_input_is_not_normalized(earnings, capital):
    with pytest.raises(ValueError):
        calculate_cumulative_return(earnings, capital)


def test_percentage_preserves_precision_and_ambient_context():
    numerator = D('12345678901234567890.000000000000000001')
    denominator = D('987654321.00000000000000000003')
    expected = expected_percent(numerator, denominator, precision=division_precision((numerator, denominator)))
    with localcontext() as ambient:
        ambient.prec = 3
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        flags = dict(ambient.flags)
        assert calculate_cumulative_return(numerator, denominator) == expected
        assert ambient.prec == 3 and ambient.flags == flags


def test_legacy_initial_funding_counts_as_paid_in_capital(ledger):
    db.session.add(PortfolioEvent(
        portfolio_id=ledger.pid, event_type='Initial', amount_delta=D('1000'), date=day(1),
    ))
    db.session.commit()
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'ONLY', D('50'), day(2))
    portfolio, total = state(ledger)
    assert portfolio.metrics['paid_in_capital'] == total.totals['paid_in_capital'] == D('1000')
    assert total.totals['capital_return'] == D('5')


def test_baseline_closure_withdrawals_redeposit_and_new_funding(ledger):
    funding = ledger.svc.portfolio_service
    funding.deposit_funds(ledger.pid, D('1000'), date=day(1))
    trade(ledger, 'Buy', '1000')
    sale = trade(ledger, 'Sell', '2000', n=3)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('500'), day(3))
    before, total = state(ledger)
    assert before.metrics['book_value'] == D('2500')
    assert before.metrics['total_realized_earnings'] == D('1500')
    assert before.asset('BTC').metrics['purchase_cost_return'] == D('150')
    assert before.asset('BTC').transaction_projections[sale.id].realized_trading_return == D('100')
    assert before.metrics['capital_return'] == total.totals['capital_return'] == D('150')
    for amount, n in [('1000', 4), ('1500', 5)]:
        funding.withdraw_funds(ledger.pid, D(amount), date=day(n))
        current, total = state(ledger)
        assert current.metrics['paid_in_capital'] == D('1000')
        assert current.metrics['capital_return'] == total.totals['capital_return'] == D('150')
    assert current.net_contributions == D('-1500')
    assert current.metrics['book_value'] == D('0')
    funding.deposit_funds(ledger.pid, D('1000'), date=day(6))
    current, total = state(ledger)
    assert current.net_contributions == D('-500')
    assert current.metrics['capital_return'] == total.totals['capital_return'] == D('75')
    funding.deposit_funds(ledger.pid, D('1000'), date=day(7))
    current, total = state(ledger)
    assert current.metrics['paid_in_capital'] == D('3000')
    assert current.metrics['capital_return'] == total.totals['capital_return'] == D('50')
    assert before.metrics['capital_return'] == D('150')  # prior snapshot stays immutable


def test_transfer_round_trips_and_unequal_portfolios_do_not_dilute_account(ledger):
    svc = ledger.svc
    destination = svc.portfolio_service.create_portfolio('Other', user_id=ledger.uid)
    svc.portfolio_service.deposit_funds(ledger.pid, D('1000'), date=day(1))
    svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('1500'), day(2))
    outgoing = svc.transfer_service.create(ledger.pid, destination.id, D('1000'), date=day(3))
    svc.transaction_service.add_dividend(destination.id, 'ONLY', D('100'), day(4))
    returning = svc.transfer_service.create(destination.id, ledger.pid, D('1000'), date=day(5))
    origin, total = state(ledger)
    other = next(p for p in total.portfolios if p.portfolio_id == destination.id)
    assert origin.metrics['paid_in_capital'] == D('2000')
    assert origin.metrics['capital_return'] == D('75')
    assert other.gross_deposits == D('0')
    assert other.metrics['paid_in_capital'] == D('1000')
    assert other.metrics['capital_return'] == D('10')
    assert total.totals['paid_in_capital'] == D('1000')
    assert total.totals['total_realized_earnings'] == D('1600')
    assert total.totals['capital_return'] == D('160')
    svc.transfer_service.update(returning.id, amount=D('500'))
    origin, edited = state(ledger)
    assert origin.metrics['capital_return'] == D('100')
    assert edited.totals['capital_return'] == D('160')
    svc.transfer_service.delete(returning.id)
    svc.transfer_service.delete(outgoing.id)
    origin, deleted = state(ledger)
    assert origin.metrics['capital_return'] == D('150')
    assert deleted.totals['capital_return'] == D('160')


def test_reinvesting_profit_and_dividends_only_changes_asset_purchase_base(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'), date=day(1))
    trade(ledger, 'Buy', '1000')
    trade(ledger, 'Sell', '2000', n=3)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('500'), day(3))
    trade(ledger, 'Buy', '2500', n=4)
    portfolio, total = state(ledger)
    asset = portfolio.asset('BTC')
    assert asset.transactions['total_purchase_cost'] == D('3500')
    assert asset.transactions['position_cost_basis'] == D('2500')
    assert asset.metrics['purchase_cost_return'] == expected_percent('1500', '3500')
    assert portfolio.metrics['capital_return'] == total.totals['capital_return'] == D('150')


@pytest.mark.parametrize('n', [3, 20])
def test_fractional_partial_full_sales_and_fees_have_duration_independent_returns(ledger, n):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'), date=day(1))
    trade(ledger, 'Buy', '99', '10', fees='10')
    trade(ledger, 'Sell', '120', '2.5', n=n, fees='5')
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('5'), day(n))
    portfolio, _ = state(ledger)
    assert portfolio.asset('BTC').transactions['position_cost_basis'] == D('750')
    assert portfolio.asset('BTC').metrics['purchase_cost_return'] == D('5')
    trade(ledger, 'Sell', '80', '7.5', n=n + 1, fees='5')
    portfolio, total = state(ledger)
    assert portfolio.asset('BTC').transactions['position_cost_basis'] == D('0')
    assert portfolio.metrics['total_realized_earnings'] == D('-105')
    assert portfolio.asset('BTC').metrics['purchase_cost_return'] == D('-10.5')
    assert total.totals['capital_return'] == D('-10.5')


@pytest.mark.parametrize('funding', ['0', '1000'])
def test_dividend_only_edits_deletes_and_empty_return(ledger, funding):
    if D(funding):
        ledger.svc.portfolio_service.deposit_funds(ledger.pid, D(funding), date=day(1))
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'ONLY', D('50'), day(2))
    dividend = ledger.svc.dividend_repo.get_by_portfolio_id(ledger.pid)[0]
    for amount in ('50', '75', '0'):
        if amount == '75':
            ledger.svc.transaction_service.update_dividend(dividend.id, amount=D(amount))
        elif amount == '0':
            ledger.svc.transaction_service.delete_dividend(dividend.id)
        portfolio, total = state(ledger)
        assert portfolio.metrics['total_realized_earnings'] == D(amount)
        assert portfolio.metrics['book_value'] == exact_add(D(funding), D(amount))
        assert portfolio.asset('ONLY').metrics['purchase_cost_return'] is None
        assert total.totals['capital_return'] == (expected_percent(amount, funding) if D(funding) else None)


@pytest.mark.parametrize('sale_price,pnl,asset_return,capital_return,tone', [
    ('110', '+15.00', '+15.00%', '+7.50%', 'pos'),
    ('80', '-15.00', '-15.00%', '-7.50%', 'neg'),
    ('95', '0.00', '0.00%', '0.00%', 'flat'),
    (None, '+5.00', '—', '—', 'flat'),
])
def test_pages_render_scope_specific_returns_and_signs(ledger, app, sale_price, pnl, asset_return, capital_return, tone):
    if sale_price is not None:
        ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('200'), date=day(1))
        trade(ledger, 'Buy', '100')
        trade(ledger, 'Sell', sale_price, n=3)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('5'), day(4))
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    overview = client.get('/').get_data(as_text=True)
    hero_pnl = re.search(r'class="hero-figure__pnl-value">(.*?)</span>', overview, re.S).group(1)
    assert f'>{pnl}' in hero_pnl
    assert f'delta delta--{tone}' in overview
    portfolio_return = re.search(r'data-label="Return">(.*?)</div>', overview, re.S).group(1)
    assert f'>{capital_return}</span>' in portfolio_return
    assets = client.get('/transactions/').get_data(as_text=True)
    summary = re.search(r'class="disclosure__metrics disclosure__metrics--assets">(.*?)</button>', assets, re.S).group(1)
    assert f'>{pnl}</span>' in summary
    assert f'>{asset_return}</span>' in summary
    if sale_price is not None:
        assert '>Realized P&amp;L</th>' in assets
        assert 'aria-label="Return" title="Return">Return</th>' in assets


def test_api_exact_fields_read_only_and_cross_user_isolation(ledger, app):
    amount = D('1000.00000000000000000001')
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, amount, date=day(1))
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('50'), day(2))
    stranger = User(username='capital-other', email='capital-other@example.com', is_verified=True)
    db.session.add(stranger)
    db.session.commit()
    svc = Services(user_id=stranger.id)
    private = svc.portfolio_service.create_portfolio('Private', user_id=stranger.id)
    svc.portfolio_service.deposit_funds(private.id, D('9000'), date=day(1))
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    statements = []
    def record(_conn, _cursor, statement, *_args):
        statements.append(statement.lstrip().upper())
    with event_listener(db.engine, record):
        response = client.get('/api/portfolio-summary')
        denied = PC.get_portfolio_snapshot(private.id, user_id=ledger.uid)
    assert response.status_code == 200
    rows = response.get_json()['portfolio_summary']
    assert len(rows) == 1
    assert rows[0]['paid_in_capital'] == str(amount)
    assert D(rows[0]['capital_return']) == expected_percent('50', amount, precision=division_precision((D('50'), amount)))
    assert rows[0]['realized_trading_return'] is None
    assert denied.metrics['paid_in_capital'] == D('0')
    assert denied.metrics['capital_return'] is None
    assert not any(s.startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for s in statements)


# The listener is scoped so assertions cannot leave SQL instrumentation installed.
@contextmanager
def event_listener(engine, listener):
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        yield
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
