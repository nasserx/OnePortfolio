"""Phase 1 characterization: current behavior, including named known defects.

Remaining defect tests assert observed behavior without xfail markers. The
Assets ordering characterization became a correctness regression in Phase 2.
All persistence uses the existing isolated ``app`` fixture.
"""

from datetime import datetime
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from types import SimpleNamespace

import pytest
from flask import g

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.models import Transaction
from portfolio_app.models.user import User
from portfolio_app.routes.transactions import _get_transactions_page_context
from portfolio_app.routes.portfolios import _get_portfolios_page_context
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES
from tests._financial import assert_accounting_invariants
from tests._auth import authenticate_client


D = Decimal


@pytest.fixture
def ledger(app):
    with app.app_context():
        user = User(username='baseline', email='baseline@example.com', is_verified=True)
        db.session.add(user)
        db.session.commit()
        svc = Services(user_id=user.id)
        portfolio = svc.portfolio_service.create_portfolio('Baseline', user_id=user.id)
        yield SimpleNamespace(uid=user.id, svc=svc, pid=portfolio.id)


def _trade(ledger, kind, price, quantity, day, fees='0', symbol='BTC'):
    return ledger.svc.transaction_service.add_transaction(
        portfolio_id=ledger.pid, transaction_type=kind, symbol=symbol,
        price=D(price), quantity=D(quantity), fees=D(fees),
        date=datetime(2024, 1, day),
    )


def _assert_btc_state(ledger, expected):
    summary = PC.get_symbol_transactions_summary(ledger.pid, 'BTC', user_id=ledger.uid)
    dashboard = PC.get_portfolio_dashboard_totals(user_id=ledger.uid)
    # Cash, net funding, quantity, open basis, trading P&L, income, book value.
    actual = (
        dashboard['total_cash'], dashboard['total_capital'],
        summary['total_quantity_held'], summary['cost_basis'],
        dashboard['realized_pnl'], dashboard['total_income'], dashboard['total_value'],
    )
    assert actual == tuple(map(D, expected))
    assert summary['realized_pnl'] == dashboard['realized_pnl']
    assert_accounting_invariants(
        summary, cash=dashboard['total_cash'], net_funding=dashboard['total_capital'],
        income=dashboard['total_income'], book_value=dashboard['total_value'],
    )
    return dashboard


def test_btc_unfunded_buy_funding_sale_withdrawal_and_profit_redeposit(ledger):
    _trade(ledger, 'Buy', '185000', '0.003', 1)
    _assert_btc_state(ledger, ('-555', '0', '0.003', '555', '0', '0', '0'))
    assert ledger.svc.portfolio_event_repo.get_by_portfolio_id(ledger.pid) == []

    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('555'), date=datetime(2024, 1, 2))
    _assert_btc_state(ledger, ('0', '555', '0.003', '555', '0', '0', '555'))

    sale = _trade(ledger, 'Sell', '186000', '0.003', 3)
    after_sale = _assert_btc_state(ledger, ('558', '555', '0', '0', '3', '0', '558'))
    assert sale.net_amount == D('558')
    trade_return = D('3') / D('555') * D('100')
    assert sale.net_pnl_percent == trade_return
    assert after_sale['return_percent'] == trade_return

    maximum = PC.get_available_cash_for_portfolio(ledger.pid, user_id=ledger.uid)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, maximum, date=datetime(2024, 1, 4))
    after_withdrawal = _assert_btc_state(ledger, ('0', '-3', '0', '0', '3', '0', '0'))
    assert after_withdrawal['total_contributed'] == D('555')
    assert after_withdrawal['return_percent'] == trade_return

    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('3'), date=datetime(2024, 1, 5))
    final = _assert_btc_state(ledger, ('3', '0', '0', '0', '3', '0', '3'))
    assert final['total_contributed'] == D('558')
    assert final['return_percent'] == D('3') / D('558') * D('100')
    assert sale.net_pnl_percent == trade_return
    assert final['return_percent'] != sale.net_pnl_percent
    # The same rounded display must not conceal the distinct denominators.
    assert final['return_display'] == '+0.54%'
    assert f'{sale.net_pnl_percent:+,.2f}%' == '+0.54%'


def test_historical_insertion_agrees_across_calculators_pages_apis_and_stored_sale(ledger, app):
    _trade(ledger, 'Buy', '100', '1', 1)
    sale = _trade(ledger, 'Sell', '150', '1', 3)
    assert sale.net_pnl == D('50')
    _trade(ledger, 'Buy', '200', '1', 2)

    summary = PC.get_symbol_transactions_summary(ledger.pid, 'BTC', user_id=ledger.uid)
    assert summary['total_quantity_held'] == D('1')
    assert summary['cost_basis'] == D('150')
    assert summary['average_cost'] == D('150')
    assert summary['realized_pnl'] == D('0')
    db.session.refresh(sale)
    assert sale.average_cost == D('150')
    assert sale.net_pnl == D('0')

    g._services = ledger.svc
    assets = _get_transactions_page_context()['holdings'][0]['summary']
    portfolio = _get_portfolios_page_context()['portfolio_details'][0]
    overview, _ = ledger.svc.overview_service.get_portfolio_summary()
    dashboard = ledger.svc.overview_service.get_portfolio_dashboard_totals()
    performance = ledger.svc.overview_service.get_symbol_performance()[0]
    assert assets == {**summary,
        'return_amount': D('0'), 'return_percent': D('0'), 'return_display': '+0.00%',
    }
    for row in (portfolio, overview[0]):
        assert row['positions'] == D('150')
        assert row['realized_pnl'] == D('0')
    assert dashboard['total_positions'] == D('150')
    assert dashboard['realized_pnl'] == performance['realized_pnl'] == D('0')
    assert performance['held_cost_basis'] == D('150')

    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.get('/api/portfolio-summary')
    assert response.status_code == 200
    api_row = response.get_json()['portfolio_summary'][0]
    assert D(str(api_row['positions'])) == D('150')
    assert D(str(api_row['realized_pnl'])) == D('0')
    holdings = client.get('/api/holdings', query_string={'portfolio_id': ledger.pid, 'symbol': 'BTC'})
    assert holdings.status_code == 200
    assert D(holdings.get_json()['held_quantity']) == D('1')


@pytest.mark.parametrize('reverse_display', [False, True])
def test_assets_and_overview_agree_regardless_of_repository_or_display_order(
    ledger, monkeypatch, reverse_display,
):
    first = _trade(ledger, 'Buy', '100', '1', 1)
    sale = _trade(ledger, 'Sell', '150', '1', 3)
    historical = _trade(ledger, 'Buy', '200', '1', 2)
    # Neither insertion order nor newest-first display order is accounting order.
    supplied = [first, sale, historical]
    if reverse_display:
        supplied.sort(key=lambda row: row.date, reverse=True)
    original_ids = [row.id for row in supplied]

    def insertion_order(portfolio_id):
        assert portfolio_id == ledger.pid
        return supplied

    monkeypatch.setattr(ledger.svc.transaction_repo, 'get_by_portfolio_id', insertion_order)
    g._services = ledger.svc
    holding = _get_transactions_page_context()['holdings'][0]
    assets = holding['summary']
    overview, _ = ledger.svc.overview_service.get_portfolio_summary()

    assert overview[0]['positions'] == D('150')
    assert overview[0]['realized_pnl'] == D('0')
    assert assets['total_quantity_held'] == D('1')
    assert assets['cost_basis'] == assets['average_cost'] == D('150')
    assert assets['realized_pnl'] == overview[0]['realized_pnl'] == D('0')
    assert sale.net_pnl == D('0')
    assert [row.id for row in supplied] == original_ids
    assert [row.id for row in holding['transactions']] == list(reversed(original_ids))


def test_persisted_ten_decimal_average_differs_from_fresh_replay(ledger):
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        _trade(ledger, 'Buy', '1', '1', 1)
        _trade(ledger, 'Buy', '2', '2', 2)
        sale = _trade(ledger, 'Sell', '3', '1', 3)
        sale_id = sale.id
        # Discard the identity map: assert persisted values, not assigned Decimals.
        db.session.expunge_all()
        persisted = db.session.get(Transaction, sale_id)
        fresh = PC.get_symbol_transactions_summary(ledger.pid, 'BTC', user_id=ledger.uid)
        assert persisted.average_cost == D('1.6666666667')
        assert persisted.net_pnl == D('1.3333333333')
        assert fresh['realized_cost_basis'] == D('5') / D('3')
        assert fresh['realized_pnl'] == D('1.333333333333333333333333333')
        assert D('0') < fresh['realized_pnl'] - persisted.net_pnl < D('1E-10')


def test_current_unfunded_buy_acceptance_but_cost_increasing_edit_is_rejected(ledger):
    buy = _trade(ledger, 'Buy', '10', '1', 1)
    assert PC.get_available_cash_for_portfolio(ledger.pid) == D('-10')
    with pytest.raises(ValueError) as error:
        ledger.svc.transaction_service.update_transaction(buy.id, price=D('11'))
    assert str(error.value) == MESSAGES['INSUFFICIENT_AMOUNT']
    db.session.refresh(buy)
    assert buy.price == D('10')
    assert PC.get_available_cash_for_portfolio(ledger.pid) == D('-10')
    # Removing this independent buy is allowed and reverses its cash effect.
    ledger.svc.transaction_service.delete_transaction(buy.id)
    assert PC.get_available_cash_for_portfolio(ledger.pid) == D('0')


def test_current_return_bases_and_unused_deposit_dilution(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('2000'), date=datetime(2024, 1, 1))
    _trade(ledger, 'Buy', '100', '10', 2)
    sale = _trade(ledger, 'Sell', '120', '5', 3)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('75'), datetime(2024, 1, 4))
    before = PC.get_portfolio_dashboard_totals(user_id=ledger.uid)
    asset_before = ledger.svc.overview_service.get_symbol_performance()[0]
    trade_return = sale.net_pnl_percent
    assert trade_return == D('100') / D('500') * D('100') == D('20')
    assert asset_before['return_percent'] == D('175') / D('1000') * D('100') == D('17.5')
    assert before['return_percent'] == D('175') / D('2000') * D('100') == D('8.75')

    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('2000'), date=datetime(2024, 1, 5))
    after = PC.get_portfolio_dashboard_totals(user_id=ledger.uid)
    portfolios, _ = ledger.svc.overview_service.get_portfolio_summary()
    asset_after = ledger.svc.overview_service.get_symbol_performance()[0]
    assert after['return_percent'] == D('175') / D('4000') * D('100') == D('4.375')
    assert portfolios[0]['return_percent'] == after['return_percent']
    assert after['total_cash'] - before['total_cash'] == D('2000')
    for key in ('realized_pnl', 'total_income', 'total_positions', 'return_amount'):
        assert after[key] == before[key]
    assert asset_after == asset_before
    assert sale.net_pnl_percent == trade_return


@pytest.mark.parametrize('quantity, persisted_quantity', [
    ('0.0000000001', '0.0000000001'),
    ('0.00000000001', '0'),
])
def test_sqlite_numeric_quantity_scale_characterization(ledger, quantity, persisted_quantity):
    """SQLite/SQLAlchemy environment characterization, not a portable SQL claim.

    SQLite accepts a positive sub-scale value, but Numeric(20,10) conversion on
    reload can expose zero. Pure-calculator precision is tested separately.
    """
    assert db.engine.dialect.name == 'sqlite'
    row = _trade(ledger, 'Buy', '1', quantity, 1)
    row_id = row.id
    db.session.expunge_all()
    persisted = db.session.get(Transaction, row_id)
    assert isinstance(persisted.quantity, Decimal)
    assert persisted.quantity == D(persisted_quantity)


@pytest.mark.parametrize('prices, price_places, average_places', [
    (('100',), 0, 2),
    (('0.0002344000',), 7, 7),
    (('12.3400', '12.3456'), 4, 4),
])
def test_asset_price_and_average_display_precision_follows_recorded_prices(
    ledger, prices, price_places, average_places,
):
    for day, price in enumerate(prices, start=1):
        _trade(ledger, 'Buy', price, '1', day)
    g._services = ledger.svc
    holding = _get_transactions_page_context()['holdings'][0]
    assert holding['price_decimal_places'] == price_places
    assert holding['avg_cost_decimal_places'] == average_places


def test_quantity_walk_and_recalculation_preserve_buy_first_when_clock_times_disagree(ledger):
    buy = ledger.svc.transaction_service.add_transaction(
        portfolio_id=ledger.pid, transaction_type='Buy', symbol='BTC',
        price=D('100'), quantity=D('1'), fees=D('0'), date=datetime(2024, 1, 1, 20),
    )
    # Accepted despite an earlier clock time: both effective dates are Jan 1.
    sale = ledger.svc.transaction_service.add_transaction(
        portfolio_id=ledger.pid, transaction_type='Sell', symbol='BTC',
        price=D('150'), quantity=D('1'), fees=D('0'), date=datetime(2024, 1, 1, 8),
    )
    assert sale.net_pnl == D('50')
    ledger.svc.transaction_service.update_transaction(buy.id, date=datetime(2024, 1, 1, 23))
    replayed = PC.recalculate_all_averages_for_symbol(ledger.pid, 'BTC', user_id=ledger.uid)
    assert [row.id for row in replayed] == [buy.id, sale.id]
    assert sale.average_cost == D('100')
    assert sale.net_pnl == D('50')
