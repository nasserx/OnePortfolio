"""Canonical row accounting shares one replay with aggregate accounting."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from html import unescape
from itertools import permutations
import re
from types import SimpleNamespace

import pytest
from flask import g
from sqlalchemy import event

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import replay_symbol_transactions
from portfolio_app.calculators.financial_snapshots import build_asset_snapshot
from portfolio_app.models import Transaction
from portfolio_app.routes.transactions import _get_transactions_page_context
from portfolio_app.utils.decimal_utils import decimal_text
from tests._auth import authenticate_client
from tests.test_financial_baseline import ledger, _trade
from tests._financial import expected_percent
from portfolio_app.utils.financial_arithmetic import exact_sum


def _row(identifier, kind, price, quantity='1', fee='0', day=None, hour=0):
    return SimpleNamespace(
        id=identifier, portfolio_id=1, symbol='BTC', transaction_type=kind,
        price=D(price), quantity=D(quantity), fees=D(fee),
        date=datetime(2024, 1, day or identifier, hour),
    )


def _assert_projection_totals(asset):
    projections = tuple(asset.transaction_projections.values())
    sales = [row for row in projections if row.transaction_type == 'Sell']
    summary = asset.transactions
    assert exact_sum(row.realized_trading_pnl for row in sales) == summary['realized_pnl']
    assert exact_sum(row.released_cost_basis for row in sales) == summary['realized_cost_basis']
    assert exact_sum(row.net_sale_proceeds for row in sales) == summary['realized_proceeds']
    assert summary['realized_proceeds'] == summary['total_sell_cost']
    assert exact_sum(row.purchase_cost for row in projections) == summary['total_buy_cost']
    if projections:
        assert projections[-1].post_quantity == summary['total_quantity_held']
        assert projections[-1].post_cost_basis == summary['cost_basis']
        assert projections[-1].post_average_unit_cost == summary['average_cost']


def test_projections_are_deterministic_for_all_retrieval_orders_and_same_day_ties():
    rows = [
        _row(9, 'Buy', '100', day=1, hour=23),
        _row(3, 'Buy', '200', day=2, hour=20),
        _row(4, 'Buy', '300', day=2, hour=8),
        _row(1, 'Sell', '250', day=2, hour=22),
        _row(2, 'Sell', '150', day=2, hour=1),
    ]
    expected = build_asset_snapshot('BTC', rows)
    assert list(expected.transaction_projections) == [9, 3, 4, 1, 2]
    assert expected.transaction_projections[1].realized_trading_pnl == D('50')
    assert expected.transaction_projections[2].realized_trading_pnl == D('-50')
    for supplied in permutations(rows):
        original_ids = [row.id for row in supplied]
        actual = build_asset_snapshot('BTC', supplied)
        assert actual == expected
        _assert_projection_totals(actual)
        assert [row.id for row in supplied] == original_ids


def test_buy_partial_sale_and_final_sale_projections_include_fees_and_pools():
    asset = build_asset_snapshot('BTC', [
        _row(1, 'Buy', '10', '2', '1'),
        _row(2, 'Buy', '12', '3', '1.5'),
        _row(3, 'Sell', '15', '2', '1'),
        _row(4, 'Sell', '14', '3', '0.9'),
    ])
    first, second, partial, final = asset.transaction_projections.values()
    assert (first.gross_amount, first.fee, first.purchase_cost, first.cash_effect) == (
        D('20'), D('1'), D('21'), D('-21'),
    )
    assert (first.post_quantity, first.post_cost_basis, first.post_average_unit_cost) == (
        D('2'), D('21'), D('10.5'),
    )
    assert first.realized_trading_pnl is first.trade_return_percent is None
    assert first.applicable_average_unit_cost == first.post_average_unit_cost
    assert second.post_cost_basis == D('58.5')
    assert second.post_average_unit_cost == D('11.7')
    assert (partial.gross_amount, partial.net_sale_proceeds, partial.released_cost_basis,
            partial.realized_trading_pnl, partial.post_quantity, partial.post_cost_basis) == (
        D('30'), D('29'), D('23.4'), D('5.6'), D('3'), D('35.1'),
    )
    assert partial.trade_return_percent == expected_percent('5.6', '23.4')
    assert partial.applicable_average_unit_cost == D('11.7')
    assert final.cash_amount == final.cash_effect == final.net_sale_proceeds == D('41.1')
    assert final.realized_trading_pnl == D('6')
    assert final.released_cost_basis == D('35.1')
    assert final.post_quantity == final.post_cost_basis == final.post_average_unit_cost == D('0')
    assert asset.transactions['realized_pnl'] == D('11.6')
    _assert_projection_totals(asset)


def test_repeated_sales_with_intervening_buy_reconcile_each_contribution():
    asset = build_asset_snapshot('BTC', [
        _row(1, 'Buy', '10', '10'), _row(2, 'Sell', '12', '4', '1'),
        _row(3, 'Buy', '13', '4', '2'), _row(4, 'Sell', '11', '5', '0.5'),
    ])
    assert asset.transaction_projections[2].realized_trading_pnl == D('7')
    assert asset.transaction_projections[4].realized_trading_pnl == D('-2.5')
    assert asset.transactions['realized_pnl'] == D('4.5')
    _assert_projection_totals(asset)


@pytest.mark.parametrize('quantity, pnl, basis', [
    ('1', '1.' + '3' * 55, '3.' + '3' * 55),
    ('3', '4', '0'),
])
def test_repeating_average_row_is_exact_aggregate_contribution(quantity, pnl, basis):
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        asset = build_asset_snapshot('BTC', [
            _row(1, 'Buy', '1'), _row(2, 'Buy', '2', '2'), _row(3, 'Sell', '3', quantity),
        ])
        sale = asset.transaction_projections[3]
        assert sale.realized_trading_pnl == asset.transactions['realized_pnl'] == D(pnl)
        assert sale.post_cost_basis == D(basis)
        assert sale.trade_return_percent == expected_percent(pnl, sale.released_cost_basis)
        _assert_projection_totals(asset)


def test_btc_projection_is_reconciled_through_funding_withdrawal_and_redeposit(ledger):
    _trade(ledger, 'Buy', '185000', '0.003', 1)
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('555'))
    sale = _trade(ledger, 'Sell', '186000', '0.003', 3)
    before = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    row = before.asset('BTC').transaction_projections[sale.id]
    assert row.net_sale_proceeds == row.cash_amount == row.cash_effect == D('558')
    assert row.released_cost_basis == D('555')
    assert row.realized_trading_pnl == before.transactions['realized_pnl'] == D('3')
    assert row.trade_return_percent == expected_percent('3', '555')
    assert row.post_quantity == row.post_cost_basis == row.post_average_unit_cost == D('0')
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('558'))
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('3'))
    after = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert after.asset('BTC').transaction_projections[sale.id] == row
    assert after.cash_balance == after.metrics['book_value'] == D('3')
    assert after.metrics['return_percent'] == expected_percent('3', '558')


def _html_trade_row(html, transaction_id):
    return next(row for row in re.findall(r'<tr\b[^>]*>.*?</tr>', html, re.S)
                if f'data-tx-id="{transaction_id}"' in row)


def test_raw_only_rows_drive_replay_display_and_serialization(ledger, app):
    buy = _trade(ledger, 'Buy', '100', '2', 1, fees='2')
    sale = _trade(ledger, 'Sell', '120', '1', 2, fees='1')
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    before = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    html_before = client.get('/transactions/').get_data(as_text=True)
    assert not hasattr(Transaction, 'average_cost')
    assert not hasattr(Transaction, 'net_amount')
    db.session.expire_all()
    after = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert after == before
    projection = after.asset('BTC').transaction_projections[sale.id]
    assert projection.realized_trading_pnl == after.transactions['realized_pnl'] == D('18')
    assert projection.released_cost_basis == D('101')
    assert projection.trade_return_percent == expected_percent('18', '101')
    assert after.cash_balance == D('-83')
    serialized = sale.to_dict(projection=projection, portfolio_name=after.name)
    assert D(serialized['net_amount']) == D('119')
    assert D(serialized['average_cost']) == D('101')
    assert D(serialized['net_pnl']) == D('18')
    assert D(serialized['net_pnl_percent']) == projection.trade_return_percent
    html_after = client.get('/transactions/').get_data(as_text=True)
    for record in (buy, sale):
        assert _html_trade_row(html_after, record.id) == _html_trade_row(html_before, record.id)
    sale_text = unescape(re.sub(r'<[^>]+>', ' ', _html_trade_row(html_after, sale.id)))
    assert '119.00' in sale_text and '+18.00' in sale_text and '+17.82%' in sale_text
    api = client.get('/api/portfolio-summary').get_json()['portfolio_summary'][0]
    assert D(api['realized_pnl']) == D('18') and D(api['cash']) == D('-83')


def test_replay_and_serializer_work_without_derived_columns_or_queries(ledger):
    _trade(ledger, 'Buy', '1', '1', 1)
    _trade(ledger, 'Buy', '2', '2', 2)
    _trade(ledger, 'Sell', '3', '1', 3)
    db.session.expunge_all()
    records = Transaction.query.order_by(Transaction.id).all()
    statements = []

    def record_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', record_sql)
    try:
        asset = build_asset_snapshot('BTC', records)
        payloads = [row.to_dict(projection=asset.transaction_projections[row.id], portfolio_name='Baseline')
                    for row in records]
    finally:
        event.remove(db.engine, 'before_cursor_execute', record_sql)
    assert statements == []
    assert payloads[0]['net_pnl'] is payloads[0]['net_pnl_percent'] is None
    assert payloads[-1]['net_pnl'] == '1.' + '3' * 55
    assert payloads[-1]['average_cost'] == '1.' + '6' * 54 + '7'
    assert isinstance(payloads[-1]['id'], int)


def test_serializer_requires_explicit_matching_projection_and_has_no_legacy_pnl_properties(ledger):
    first = _trade(ledger, 'Buy', '1', '1', 1)
    second = _trade(ledger, 'Buy', '2', '1', 2)
    snapshot = PC.get_asset_snapshot(ledger.pid, 'BTC')
    assert not hasattr(Transaction, 'net_pnl')
    assert not hasattr(Transaction, 'net_pnl_percent')
    with pytest.raises(TypeError):
        first.to_dict()
    with pytest.raises(ValueError, match='does not belong'):
        first.to_dict(projection=snapshot.transaction_projections[second.id], portfolio_name='Baseline')


def test_historical_insertion_updates_canonical_rows_without_changing_display_order(ledger, app):
    buy = _trade(ledger, 'Buy', '100', '1', 1)
    sale = _trade(ledger, 'Sell', '150', '1', 3)
    old = PC.get_asset_snapshot(ledger.pid, 'BTC').transaction_projections[sale.id]
    assert old.realized_trading_pnl == D('50')
    historical = _trade(ledger, 'Buy', '200', '1', 2)
    with app.test_request_context():
        g._services = ledger.svc
        holding = _get_transactions_page_context()['holdings'][0]
    rows = holding['transaction_projections']
    assert list(rows) == [buy.id, historical.id, sale.id]
    # Current presentation reverses repository order (insertion order here),
    # independently of effective-date replay. This phase does not redesign it.
    assert [row.id for row in holding['transactions']] == [historical.id, sale.id, buy.id]
    assert rows[sale.id].post_cost_basis == rows[sale.id].applicable_average_unit_cost == D('150')
    assert rows[sale.id].post_quantity == D('1')
    assert rows[sale.id].realized_trading_pnl == holding['summary']['realized_pnl'] == D('0')
    assert old.realized_trading_pnl == D('50')  # Detached previous read remains stable.


def test_assets_batch_read_replays_once_and_query_count_does_not_grow_with_rows(ledger, app, monkeypatch):
    import portfolio_app.calculators.financial_snapshots as engine
    original = engine.replay_symbol_transactions
    calls = []

    def counted(records):
        calls.append(len(records))
        return original(records)

    monkeypatch.setattr(engine, 'replay_symbol_transactions', counted)
    counts = []
    for number in (1, 8):
        for day in range(1 if number == 1 else 2, number + 1):
            _trade(ledger, 'Buy', '100', '1', day)
        statements = []

        def record_sql(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        calls.clear()
        event.listen(db.engine, 'before_cursor_execute', record_sql)
        try:
            with app.test_request_context():
                g._services = ledger.svc
                holding = _get_transactions_page_context()['holdings'][0]
                for row in holding['transactions']:
                    row.to_dict(projection=holding['transaction_projections'][row.id], portfolio_name='Baseline')
        finally:
            event.remove(db.engine, 'before_cursor_execute', record_sql)
        assert calls == [number]
        counts.append(len(statements))
    assert counts[0] == counts[1]


def test_projection_values_are_immutable_and_preserve_subscale_raw_products():
    row = _row(1, 'Buy', '0.1234567891', '0.0000000001')
    asset = build_asset_snapshot('BTC', [row])
    projection = asset.transaction_projections[1]
    assert projection.cash_amount == D('0.00000000001234567891')
    assert decimal_text(projection.cash_amount) == '0.00000000001234567891'
    with pytest.raises(FrozenInstanceError):
        projection.cash_effect = D('9')
    with pytest.raises(TypeError):
        asset.transaction_projections[1] = projection
    row.price = D('99')
    assert projection.gross_amount == D('0.00000000001234567891')


def test_zero_sale_basis_keeps_undefined_return_without_trusting_stored_average():
    # Pure boundary case for legacy scale-converted records; not authorization
    # to enter a zero-price Buy through forms.
    replay = replay_symbol_transactions([
        _row(1, 'Buy', '0'), _row(2, 'Sell', '1'),
    ])
    assert replay.projections[1].released_cost_basis == D('0')
    assert replay.projections[1].trade_return_percent is None
    assert replay.projections[1].realized_trading_pnl == replay.summary['realized_pnl'] == D('1')
