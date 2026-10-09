"""Canonical aggregate reads; stored-row and precision projections stay explicit."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from tests._financial import expected_percent
from types import SimpleNamespace

import pytest
from flask import g, template_rendered
from sqlalchemy import event

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_snapshots import (
    build_asset_snapshot, build_portfolio_snapshot, build_global_snapshot,
)
from portfolio_app.routes.portfolios import _get_portfolios_page_context
from portfolio_app.routes.transactions import _get_transactions_page_context
from tests._auth import authenticate_client
from tests._financial import assert_accounting_invariants, transaction_projection
from tests.test_financial_baseline import ledger, _historical_trade


D = Decimal


def _assert_consumers(ledger, app):
    """Exact Decimal agreement before HTTP serializes financial values as text."""
    snapshot = PC.get_financial_snapshot(ledger.uid)
    rows, total = snapshot.as_portfolio_summary()
    assert ledger.svc.overview_service.get_portfolio_summary() == (rows, total)
    assert ledger.svc.overview_service.get_portfolio_dashboard_totals() == dict(snapshot.totals)
    g._services = ledger.svc
    details = {r['portfolio'].id: r for r in _get_portfolios_page_context()['portfolio_details']}
    context = _get_transactions_page_context()
    holdings = {(r['portfolio'].id, r['symbol']): r for r in context['holdings']}
    performance = {
        (r['portfolio_id'], r['symbol']): r
        for r in ledger.svc.overview_service.get_symbol_financials()
    }
    for portfolio in snapshot.portfolios:
        row = portfolio.as_portfolio_row()
        details_row = details[portfolio.portfolio_id]
        assert details_row['cash_balance'] == row['cash_balance']
        for key in ('net_contributions', 'position_cost_basis', 'book_value', 'realized_trading_pnl',
                    'dividend_income', 'total_realized_earnings', 'realized_trading_return', 'trading_return_display'):
            assert details_row[key] == row[key]
        assert_accounting_invariants(
            portfolio.transactions, cash=portfolio.cash_balance,
            net_funding=portfolio.net_contributions, dividend_income=portfolio.dividend_income,
            book_value=portfolio.metrics['book_value'],
        )
        for symbol, asset in portfolio.assets.items():
            perf = performance[(portfolio.portfolio_id, symbol)]
            assert perf == asset.as_financial_row(portfolio.portfolio_id, portfolio.name)
            # Income-only untracked symbols intentionally remain absent in Assets.
            holding = holdings.get((portfolio.portfolio_id, symbol))
            if holding:
                summary = holding['summary']
                for key, value in asset.transactions.items():
                    assert summary[key] == value
                assert summary['total_realized_earnings'] == perf['total_realized_earnings']
                if asset.transactions['released_cost_basis']:
                    assert summary['realized_trading_return'] == perf['realized_trading_return']
                else:
                    assert summary['realized_trading_return'] is None
                    assert perf['realized_trading_return'] is None
                assert summary['trading_return_display'] == perf['trading_return_display']
                assert context['dividend_totals'].get((portfolio.portfolio_id, symbol), D('0')) == asset.dividend_income

    client = app.test_client()
    authenticate_client(client, ledger.uid)
    api = client.get('/api/portfolio-summary')
    assert api.status_code == 200
    payload = api.get_json()
    assert D(str(payload['book_value'])) == total
    assert len(payload['portfolio_summary']) == len(rows)
    for actual, expected in zip(payload['portfolio_summary'], rows):
        for key in ('cash_balance', 'net_contributions', 'gross_deposits', 'position_cost_basis',
                    'position_cost_basis', 'realized_trading_pnl', 'dividend_income', 'total_realized_earnings', 'book_value'):
            assert D(str(actual[key])) == expected[key]
        assert actual['trading_return_display'] == expected['trading_return_display']
        portfolio = next(p for p in snapshot.portfolios if p.portfolio_id == actual['id'])
        for symbol, asset in portfolio.assets.items():
            response = client.get('/api/holdings', query_string={
                'portfolio_id': portfolio.portfolio_id, 'symbol': symbol,
            })
            assert response.status_code == 200
            assert D(response.get_json()['held_quantity']) == asset.transactions['total_quantity_held']

    rendered = []

    def capture(sender, template, context, **extra):
        rendered.append(context)

    with template_rendered.connected_to(capture, app):
        assert client.get('/').status_code == 200
    assert rendered[-1]['portfolio_summary'] == rows
    assert rendered[-1]['totals'] == dict(snapshot.totals)
    return snapshot


def test_btc_every_stage_agrees_across_snapshot_pages_and_apis(ledger, app):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('555'), date=datetime(2024, 1, 1))
    _historical_trade(ledger, 'Buy', '185000', '0.003', 1)
    assert _assert_consumers(ledger, app).totals['cash_balance'] == D('0')
    assert _assert_consumers(ledger, app).totals['book_value'] == D('555')
    sale = _historical_trade(ledger, 'Sell', '186000', '0.003', 3)
    assert _assert_consumers(ledger, app).totals['realized_trading_pnl'] == D('3')
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('558'))
    assert _assert_consumers(ledger, app).totals['net_contributions'] == D('-3')
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('3'))
    snapshot = _assert_consumers(ledger, app)
    assert snapshot.totals['cash_balance'] == snapshot.totals['book_value'] == D('3')
    assert snapshot.totals['realized_trading_return'] == expected_percent('3', '555')
    assert transaction_projection(sale).realized_trading_return == expected_percent('3', '555')


@pytest.mark.parametrize('sold, quantity, basis, pnl, cash, book', [
    ('2', '3', '35.1', '5.6', '972.9', '1008'),
    ('5', '0', '0', '15.5', '1017.9', '1017.9'),
])
def test_partial_and_full_sale_with_fees_income_and_multiple_buys(
    ledger, app, sold, quantity, basis, pnl, cash, book,
):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _historical_trade(ledger, 'Buy', '10', '2', 1, fees='1')
    _historical_trade(ledger, 'Buy', '12', '3', 2, fees='1.5')
    _historical_trade(ledger, 'Sell', '15', sold, 3, fees='1')
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('2.4'), datetime(2024, 1, 4))
    snapshot = _assert_consumers(ledger, app)
    asset = snapshot.portfolios[0].asset('BTC')
    assert asset.transactions['total_quantity_held'] == D(quantity)
    assert asset.transactions['position_cost_basis'] == D(basis)
    assert asset.transactions['realized_trading_pnl'] == D(pnl)
    assert snapshot.totals['cash_balance'] == D(cash)
    assert snapshot.totals['book_value'] == D(book)
    assert asset.metrics['realized_trading_return'] == expected_percent(D(pnl), asset.transactions['released_cost_basis'])


def test_multi_portfolio_same_symbol_separate_pools_and_unused_deposit_return(ledger, app):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _historical_trade(ledger, 'Buy', '100', '4', 1)
    _historical_trade(ledger, 'Sell', '140', '1', 2)
    second = ledger.svc.portfolio_service.create_portfolio('Second', user_id=ledger.uid)
    other = SimpleNamespace(pid=second.id, uid=ledger.uid, svc=ledger.svc)
    _historical_trade(other, 'Buy', '200', '2', 1)
    _historical_trade(other, 'Sell', '180', '1', 2)
    before = _assert_consumers(ledger, app)
    assert before.totals['position_cost_basis'] == D('500')
    assert before.totals['realized_trading_pnl'] == D('20')
    assert before.totals['realized_trading_return'] == expected_percent('20', '300')
    assert before.portfolios[1].cash_balance == D('-220')
    assert before.portfolios[1].metrics['trading_return_display'] == '-10.00%'
    ledger.svc.portfolio_service.deposit_funds(second.id, D('3000'))
    after = _assert_consumers(ledger, app)
    assert after.totals['realized_trading_return'] == before.totals['realized_trading_return']
    for previous, current in zip(before.portfolios, after.portfolios):
        assert previous.asset('BTC') == current.asset('BTC')


def test_dividend_only_trading_return_is_undefined_at_every_scope(ledger, app):
    ledger.svc.transaction_service.add_symbol(ledger.pid, 'BTC')
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('12.34'), datetime(2024, 1, 1))
    snapshot = _assert_consumers(ledger, app)
    portfolio = snapshot.portfolios[0]
    assert portfolio.cash_balance == portfolio.metrics['book_value'] == D('12.34')
    assert portfolio.metrics['realized_trading_return'] is None
    assert portfolio.metrics['trading_return_display'] == '—'
    assert portfolio.asset('BTC').as_assets_summary()['realized_trading_return'] is None
    assert portfolio.transactions['realized_trading_pnl'] == portfolio.transactions['position_cost_basis'] == D('0')


def test_symbol_performance_keeps_traded_rows_before_income_only_rows(ledger):
    second = ledger.svc.portfolio_service.create_portfolio('Second', user_id=ledger.uid)
    for pid in (ledger.pid, second.id):
        _historical_trade(SimpleNamespace(pid=pid, svc=ledger.svc), 'Buy', '10', '1', 1)
        ledger.svc.transaction_service.add_dividend(pid, 'ONLY', D('2'), datetime(2024, 1, 2))
    rows = PC.get_user_symbol_financials(ledger.uid)
    assert [(row['portfolio_id'], row['symbol']) for row in rows] == [
        (ledger.pid, 'BTC'), (second.id, 'BTC'),
        (ledger.pid, 'ONLY'), (second.id, 'ONLY'),
    ]


def test_new_snapshot_entry_points_retain_user_scoping_and_empty_state(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _historical_trade(ledger, 'Buy', '100', '1', 1)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('5'), datetime(2024, 1, 2))
    denied = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid + 1)
    assert denied.name == ''
    assert not denied.assets
    assert not denied.dividend_income_by_symbol
    assert denied.cash_balance == denied.net_contributions == denied.dividend_income == D('0')
    asset = PC.get_asset_snapshot(ledger.pid, 'BTC', user_id=ledger.uid + 1)
    assert asset.transactions['total_quantity_held'] == asset.dividend_income == D('0')
    empty = PC.get_financial_snapshot(ledger.uid + 1)
    assert empty.as_portfolio_summary() == ([], D('0'))
    assert empty.totals['realized_trading_return'] is None
    assert empty.totals['trading_return_display'] == '—'


def test_snapshots_are_detached_read_only_values_and_adapters_are_copies(ledger):
    _historical_trade(ledger, 'Buy', '100', '1', 1)
    snapshot = PC.get_financial_snapshot(ledger.uid)
    portfolio = snapshot.portfolios[0]
    asset = portfolio.asset('BTC')
    with pytest.raises(FrozenInstanceError):
        portfolio.cash_balance = D('99')
    for mapping in (snapshot.totals, portfolio.assets, portfolio.transactions,
                    portfolio.metrics, portfolio.dividend_income_by_symbol,
                    asset.transactions, asset.metrics):
        with pytest.raises(TypeError):
            mapping['tamper'] = D('99')
    copy = asset.as_assets_summary()
    copy['position_cost_basis'] = D('99')
    assert asset.transactions['position_cost_basis'] == D('100')
    db.session.expunge_all()
    assert portfolio.as_portfolio_row()['cash_balance'] == D('-100')
    assert asset.transactions['total_quantity_held'] == D('1')


def test_snapshot_reads_raw_facts_and_does_not_write(ledger):
    _historical_trade(ledger, 'Buy', '100', '2', 1)
    sale = _historical_trade(ledger, 'Sell', '120', '1', 2)
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        snapshot = PC.get_financial_snapshot(ledger.uid)
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert 'SELECT' in statements
    assert set(statements) <= {'SELECT', 'BEGIN', 'ROLLBACK', 'PRAGMA'}
    assert not db.session.dirty
    assert snapshot.totals['realized_trading_pnl'] == D('20')
    assert snapshot.totals['cash_balance'] == D('-80')
    db.session.refresh(sale)
    assert transaction_projection(sale).realized_trading_pnl == D('20')


def test_new_reads_reflect_edits_and_deletions_without_mutating_prior_snapshot(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _historical_trade(ledger, 'Buy', '100', '2', 1)
    sale = _historical_trade(ledger, 'Sell', '120', '1', 2)
    before = PC.get_financial_snapshot(ledger.uid)
    ledger.svc.transaction_service.update_transaction(sale.id, price=D('130'))
    edited = PC.get_financial_snapshot(ledger.uid)
    ledger.svc.transaction_service.delete_transaction(sale.id)
    deleted = PC.get_financial_snapshot(ledger.uid)
    assert [s.totals['realized_trading_pnl'] for s in (before, edited, deleted)] == list(map(D, ('20', '30', '0')))
    assert [s.totals['cash_balance'] for s in (before, edited, deleted)] == list(map(D, ('920', '930', '800')))


def test_composed_overview_replays_each_asset_only_once(ledger, app, monkeypatch):
    import portfolio_app.calculators.financial_snapshots as engine

    _historical_trade(ledger, 'Buy', '100', '1', 1, symbol='BTC')
    _historical_trade(ledger, 'Buy', '200', '1', 1, symbol='ETH')
    original = engine.replay_symbol_transactions
    calls = []

    def counted(records):
        calls.append([row.id for row in records])
        return original(records)

    monkeypatch.setattr(engine, 'replay_symbol_transactions', counted)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    assert client.get('/').status_code == 200
    assert len(calls) == 2
    assert all(len(ids) == 1 for ids in calls)


def test_sqlite_income_uses_same_loaded_decimal_rows_for_every_projection(ledger, app):
    """Every consumer sums exact persisted Decimals, never SQLite SUM."""
    assert db.engine.dialect.name == 'sqlite'
    for _ in range(2):
        ledger.svc.transaction_service.add_dividend(
            ledger.pid, 'BTC', D('0.00000000006'), datetime(2024, 1, 1),
        )
    db.session.expunge_all()
    snapshot = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert snapshot.dividend_income == snapshot.asset('BTC').dividend_income == D('0.00000000012')
    assert snapshot.dividend_income_by_symbol['BTC'] == D('0.00000000012')
    assert snapshot.asset('BTC').as_assets_summary()['total_realized_earnings'] == D('0.00000000012')
    _assert_consumers(ledger, app)


def test_pure_snapshot_composition_closes_full_liquidation_exactly():
    transactions = [
        SimpleNamespace(id=i, date=datetime(2024, 1, i), transaction_type=kind,
                        price=D(price), quantity=D(qty), fees=D('0'))
        for i, (kind, price, qty) in enumerate([
            ('Buy', '1', '1'), ('Buy', '2', '2'), ('Sell', '3', '3'),
        ], start=1)
    ]
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        asset = build_asset_snapshot('BTC', list(reversed(transactions)))
        portfolio = build_portfolio_snapshot(
            portfolio_id=1, name='Pure', assets={'BTC': asset},
            gross_deposits=D('0'), net_contributions=D('0'),
            cash_transactions=transactions, dividend_income=D('0'), dividend_income_by_symbol={},
        )
        global_state = build_global_snapshot([portfolio])
    assert asset.transactions['total_quantity_held'] == D('0')
    assert asset.transactions['position_cost_basis'] == portfolio.transactions['position_cost_basis'] == D('0')
    assert asset.transactions['realized_trading_pnl'] == global_state.totals['realized_trading_pnl'] == D('4')
