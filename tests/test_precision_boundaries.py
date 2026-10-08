"""Phase 4 action precision, with storage limitations tested separately."""

from datetime import datetime
from decimal import Decimal as D
from html import unescape
import json
import re
from types import SimpleNamespace

import pytest
from flask import g, render_template, render_template_string

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.calculators.financial_math import calculate_symbol_transaction_summary
from portfolio_app.calculators.financial_snapshots import build_asset_snapshot
from portfolio_app.forms.transaction_forms import (
    TransactionAddForm, TransactionEditForm, DividendAddForm, DividendEditForm,
)
from portfolio_app.forms.portfolio_forms import (
    PortfolioDepositForm, PortfolioWithdrawForm, PortfolioEventEditForm,
)
from portfolio_app.models import Transaction, Dividend, PortfolioEvent
from portfolio_app.routes.transactions import _get_transactions_page_context
from portfolio_app.routes.portfolios import _get_portfolios_page_context, _portfolio_modal_data
from portfolio_app.utils.decimal_utils import (
    decimal_text, parse_financial_decimal, withdrawal_max_text, to_decimal,
)
from tests._auth import authenticate_client
from tests.test_financial_baseline import ledger, _historical_trade
from tests.test_financial_snapshots import _assert_consumers


def _payloads(html, attribute):
    return [json.loads(unescape(value)) for value in re.findall(attribute + r"='([^']*)'", html)]


def _forms(value):
    portfolio = SimpleNamespace(id=1)
    return [
        TransactionAddForm(dict(portfolio_id='1', symbol='BTC', price=value,
                                quantity=value, fees=value, date='2024-01-01'), [portfolio]),
        TransactionEditForm(dict(edit_price=value, edit_quantity=value, edit_fees=value), 1, 'Buy'),
        DividendAddForm(dict(portfolio_id='1', div_symbol='BTC', amount=value, date='2024-01-01'), [portfolio]),
        DividendEditForm(dict(edit_amount=value, edit_date='2024-01-01'), 1),
        PortfolioDepositForm(dict(amount_delta=value, deposit_date='2024-01-01'), 1),
        PortfolioWithdrawForm(dict(amount_delta=value, withdraw_date='2024-01-01'), 1),
        PortfolioEventEditForm(dict(edit_cash_event_amount=value), 1),
    ]


@pytest.mark.parametrize('text, expected', [
    ('1,000', '1000'), (' +1,000.0100 ', '1000.0100'),
    ('-1,000.01', '-1000.01'), ('.125', '0.125'), ('1.', '1'),
    ('1e-10', '0.0000000001'), (' 0 ', '0'),
])
def test_shared_parser_exact_grammar(text, expected):
    assert parse_financial_decimal(text) == D(expected)


@pytest.mark.parametrize('text', ['', ' ', 'NaN', 'sNaN', 'Infinity', '-Infinity',
                                  'garbage', '1,5', '1,00', '1 000', '1_000', '1.2.3'])
def test_parser_rejects_invalid_or_nonfinite_text(text):
    with pytest.raises(ValueError):
        parse_financial_decimal(text)


@pytest.mark.parametrize('text', ['NaN', 'Infinity', '-Infinity'])
def test_all_financial_forms_reject_nonfinite_values(text):
    for form in _forms(text):
        assert not form.validate(), type(form).__name__
        assert form.errors
    with pytest.raises(ValueError):
        to_decimal(D(text))


def test_all_financial_forms_interpret_grouped_thousands_consistently():
    for form in _forms('1,000'):
        assert form.validate(), (type(form).__name__, form.errors)
        numeric = [value for value in form.cleaned_data.values() if isinstance(value, D)]
        assert numeric and all(value == D('1000') for value in numeric)


@pytest.mark.parametrize('text', ['NaN', 'Infinity', '-Infinity'])
def test_service_entry_points_reject_nonfinite_before_any_mutation(ledger, text):
    svc = ledger.svc
    svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    trade = _historical_trade(ledger, 'Buy', '10', '1', 1)
    dividend = svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('1'), datetime(2024, 1, 1))
    event_id = svc.portfolio_event_repo.get_by_portfolio_id(ledger.pid)[0].id
    bad = D(text)
    calls = [
        lambda: svc.portfolio_service.deposit_funds(ledger.pid, bad),
        lambda: svc.portfolio_service.withdraw_funds(ledger.pid, bad),
        lambda: svc.portfolio_service.update_portfolio_event(event_id, bad),
        lambda: svc.transaction_service.add_dividend(ledger.pid, 'BTC', bad, datetime(2024, 1, 1)),
        lambda: svc.transaction_service.update_dividend(dividend.id, amount=bad),
    ]
    for field in ('price', 'quantity', 'fees'):
        values = dict(price=D('1'), quantity=D('1'), fees=D('0'))
        values[field] = bad
        calls.append(lambda values=values: svc.transaction_service.add_transaction(
            ledger.pid, 'Buy', 'BTC', **values,
        ))
        calls.append(lambda field=field: svc.transaction_service.update_transaction(trade.id, **{field: bad}))
    for call in calls:
        with pytest.raises(ValueError):
            call()
        assert not db.session.new and not db.session.dirty
    assert Transaction.query.count() == Dividend.query.count() == PortfolioEvent.query.count() == 1


def test_exact_decimal_text_preserves_digits_without_context_rounding(app):
    for value in map(D, ('1234567890.1234567890', '0.0000000001', '0E-10',
                         '12345678901234567890.12345678901234567890')):
        with app.app_context():
            payload = render_template_string('{{ value|decimal_text }}', value=value)
        assert 'E' not in payload and ',' not in payload
        assert D(payload) == value


def test_actual_template_action_payloads_do_not_float_format(ledger, app):
    _historical_trade(ledger, 'Buy', '1', '1', 1)
    value = D('1234567890.1234567890')
    # Transient records isolate the template boundary. Exact database
    # persistence has separate round-trip coverage.
    row = Transaction(id=99, portfolio_id=ledger.pid, transaction_type='Buy',
                      symbol='BTC', price=value, quantity=value, fees=value,
                      date=datetime(2024, 1, 1))
    dividend = Dividend(id=99, portfolio_id=ledger.pid, symbol='BTC', amount=value,
                        date=datetime(2024, 1, 1))
    with app.test_request_context():
        g.services = ledger.svc
        from flask_login import login_user
        from portfolio_app.models import User
        login_user(db.session.get(User, ledger.uid))
        context = _get_transactions_page_context()
        context['holdings'][0]['transactions'] = [row]
        context['holdings'][0]['transaction_projections'] = build_asset_snapshot('BTC', [row]).transaction_projections
        context['dividends_by_symbol'] = {(ledger.pid, 'BTC'): [dividend]}
        html = render_template('assets.html', **context)
        payload = _payloads(html, 'data-tx')[0]
        assert all(payload[field] == decimal_text(value) for field in ('price', 'quantity', 'fees'))
        assert _payloads(html, 'data-div')[0]['amount'] == decimal_text(value)
        assert dividend.to_dict()['amount'] == decimal_text(value)
        context = _get_portfolios_page_context()
        context['portfolio_details'][0]['events'] = [PortfolioEvent(
            id=99, portfolio_id=ledger.pid, event_type='Deposit',
            amount_delta=D('1234567890123.45'), date=datetime(2024, 1, 1),
        )]
        html = render_template('portfolios.html', **context)
        assert _payloads(html, 'data-event')[0]['amount'] == '1234567890123.45'


@pytest.mark.parametrize('edit', ['notes', 'date'])
@pytest.mark.parametrize('price, quantity', [
    ('1234567890.1234567890', '0.0034567891'),
    ('0.1234567891', '1234567890.1234567890'),
])
def test_nonfinancial_trade_edit_preserves_loaded_financial_values(ledger, app, edit, price, quantity):
    row = _historical_trade(ledger, 'Buy', price, quantity, 1, fees='0.0123456789')
    row_id = row.id
    db.session.expunge_all()
    before = db.session.get(Transaction, row_id)
    expected = tuple(getattr(before, field) for field in ('price', 'quantity', 'fees'))
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    payload = _payloads(client.get('/transactions/').get_data(as_text=True), 'data-tx')[0]
    assert tuple(D(payload[field]) for field in ('price', 'quantity', 'fees')) == expected
    data = {f'edit_{field}': payload[field] for field in ('price', 'quantity', 'fees')}
    data.update(edit_symbol='BTC', edit_notes='changed' if edit == 'notes' else '',
                edit_date='2024-01-02' if edit == 'date' else '2024-01-01')
    response = client.post(f'/transactions/edit/{row_id}', data=data,
                           headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.get_json()['success'] is True
    db.session.expunge_all()
    after = db.session.get(Transaction, row_id)
    assert tuple(getattr(after, field) for field in ('price', 'quantity', 'fees')) == expected
    assert after.notes == data['edit_notes']
    assert after.date.strftime('%Y-%m-%d') == data['edit_date']


@pytest.mark.parametrize('cash, expected', [
    ('1.005', '1.00'), ('1.009', '1.00'), ('1.019', '1.01'),
    ('12.34', '12.34'), ('0', '0.00'), ('-10.01', '0.00'), ('0.009', '0.00'),
])
def test_withdrawal_max_is_executable_cent_floor(cash, expected):
    result = withdrawal_max_text(D(cash))
    assert result == expected
    assert D(result) <= max(D(cash), D('0'))


@pytest.mark.parametrize('cash', ['1.005', '1.009', '1.019', '12.34'])
def test_date_aware_max_endpoint_is_accepted_by_service(ledger, app, cash):
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D(cash), datetime(2024, 1, 1))
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    html = client.get('/portfolios/').get_data(as_text=True)
    assert 'data-withdrawable-cash-input' not in html
    amount = client.get(f'/portfolios/withdrawal-max/{ledger.pid}?date=2024-01-01').json['amount']
    assert amount == withdrawal_max_text(D(cash))
    with app.test_request_context():
        g.services = ledger.svc
        assert 'withdrawable_cash_input' not in _portfolio_modal_data(ledger.pid)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D(amount))
    assert PC.get_cash_balance_for_portfolio(ledger.pid) == D(cash) - D(amount)


def test_summary_json_preserves_high_precision_snapshot_values_and_types(ledger, app):
    _historical_trade(ledger, 'Buy', '0.1234567891', '0.0000000001', 1)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    row = client.get('/api/portfolio-summary').get_json()['portfolio_summary'][0]
    snapshot = PC.get_portfolio_snapshot(ledger.pid)
    assert isinstance(row['id'], int)
    assert isinstance(row['position_cost_basis'], str)
    assert row['position_cost_basis'] == decimal_text(snapshot.transactions['position_cost_basis']) == '0.00000000001234567891'
    assert D(row['cash_balance']) == -D(row['position_cost_basis'])
    held = client.get('/api/holdings', query_string=dict(portfolio_id=ledger.pid, symbol='BTC')).get_json()
    assert held['held_quantity'] == '0.0000000001'


def test_funding_sums_exact_loaded_values_not_sql_sum(ledger, app):
    assert db.engine.dialect.name == 'sqlite'
    for _ in range(2):
        ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('0.006'))
    # New records retain accepted sub-cent inputs, without NUMERIC scale loss.
    db.session.expunge_all()
    rows = PortfolioEvent.query.all()
    assert [row.amount_delta for row in rows] == [D('0.006'), D('0.006')]
    assert PC.get_total_deposits_for_portfolio(ledger.pid) == D('0.012')
    assert PC.get_net_contributions_for_portfolio(ledger.pid) == D('0.012')
    assert _assert_consumers(ledger, app).totals['cash_balance'] == D('0.012')


def test_nonzero_position_keeps_tiny_cost_pool():
    summary = calculate_symbol_transaction_summary([
        SimpleNamespace(transaction_type='Buy', price=D('1E-20'), quantity=D('2E-10'), fees=D('0')),
        SimpleNamespace(transaction_type='Sell', price=D('1E-20'), quantity=D('1E-10'), fees=D('0')),
    ])
    assert summary['total_quantity_held'] == D('1E-10')
    assert summary['position_cost_basis'] == D('1E-30')
    assert summary['average_unit_cost'] == D('1E-20')


def test_canonical_replay_new_buy_after_repeating_average_closure_has_clean_pool(ledger):
    _historical_trade(ledger, 'Buy', '1', '1', 1)
    _historical_trade(ledger, 'Buy', '2', '2', 2)
    _historical_trade(ledger, 'Sell', '3', '3', 3)
    _historical_trade(ledger, 'Buy', '0.1', '1', 4)
    fresh = PC.get_asset_snapshot(ledger.pid, 'BTC')
    assert list(fresh.transaction_projections.values())[-1].applicable_average_unit_cost == D('0.1')
    assert fresh.transactions['position_cost_basis'] == D('0.1')
    assert fresh.transactions['realized_trading_pnl'] == D('4')


def test_notes_only_edit_with_calendar_date_payload_does_not_replay(ledger, app, monkeypatch):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('10000000'), date=datetime(2024, 1, 1))
    row = ledger.svc.transaction_service.add_transaction(
        ledger.pid, 'Buy', 'BTC', D('1234567890.1234567890'), D('0.0034567891'),
        D('0.0123456789'), date=datetime(2024, 1, 1, 12, 34),
    )
    row_id = row.id
    db.session.expunge_all()
    before = db.session.get(Transaction, row_id)
    fields = ('price', 'quantity', 'fees')
    expected = tuple(getattr(before, field) for field in fields)

    assert not hasattr(PC, 'recalculate_all_averages_for_symbol')
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    payload = _payloads(client.get('/transactions/').get_data(as_text=True), 'data-tx')[0]
    data = {f'edit_{field}': payload[field] for field in ('price', 'quantity', 'fees')}
    data.update(edit_date=payload['dateShort'], edit_notes='metadata only')
    assert client.post(f'/transactions/edit/{row_id}', data=data,
                       headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()['success']
    db.session.expunge_all()
    after = db.session.get(Transaction, row_id)
    assert tuple(getattr(after, field) for field in fields) == expected


@pytest.mark.parametrize('kind', ['income', 'funding'])
def test_notes_only_amount_edit_preserves_loaded_amount(ledger, app, kind):
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    if kind == 'income':
        ledger.svc.transaction_service.add_symbol(ledger.pid, 'BTC')
        row = ledger.svc.transaction_service.add_dividend(
            ledger.pid, 'BTC', D('1234567890.1234567890'), datetime(2024, 1, 1),
        )
        model, field, page, attribute = Dividend, 'amount', '/transactions/', 'data-div'
        target = f'/transactions/dividends/edit/{row.id}'
    else:
        ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1234567890123.45'), date=datetime(2024, 1, 1))
        row = ledger.svc.portfolio_event_repo.get_by_portfolio_id(ledger.pid)[0]
        model, field, page, attribute = PortfolioEvent, 'amount_delta', '/portfolios/', 'data-event'
        target = f'/portfolios/events/edit/{row.id}'
    row_id = row.id
    db.session.expunge_all()
    expected = getattr(db.session.get(model, row_id), field)
    payload = _payloads(client.get(page).get_data(as_text=True), attribute)[0]
    assert D(payload['amount']) == expected
    data = (dict(edit_amount=payload['amount'], edit_date='2024-01-01', edit_notes='changed')
            if kind == 'income' else dict(edit_cash_event_amount=payload['amount'],
                                         edit_cash_event_notes='changed', date='2024-01-01'))
    response = client.post(target, data=data, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.get_json()['success']
    db.session.expunge_all()
    after = db.session.get(model, row_id)
    assert getattr(after, field) == expected
    assert after.notes == 'changed'
