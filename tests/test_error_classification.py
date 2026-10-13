"""Intrinsic input failures versus authoritative account/history failures."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from portfolio_app import db
from portfolio_app.models import Transaction, PortfolioEvent, User
from portfolio_app.services.factory import Services
from portfolio_app.services.transaction_service import TransactionService
from portfolio_app.services.portfolio_service import PortfolioService
from portfolio_app.services.transfer_service import TransferService
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.utils.auth_session import mark_recent_auth
from portfolio_app.utils.mutation_requests import issue_mutation_token
from tests.test_form_feedback import seeded_client, Markup

HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


@pytest.fixture
def forms(app):
    client, portfolio, dividend = seeded_client(app)
    with app.app_context():
        owner = db.session.get(User, Transaction.query.filter_by(portfolio_id=portfolio).one().portfolio.user_id)
        uid = owner.id
        transaction = Transaction.query.filter_by(portfolio_id=portfolio).one().id
        event = PortfolioEvent.query.filter_by(portfolio_id=portfolio).one().id
        other = Services(user_id=uid).portfolio_service.create_portfolio('Other', user_id=uid).id
    day = '2024-01-05'
    return client, uid, {
        'buy': ('/transactions/add', dict(portfolio_id=portfolio, transaction_type='Buy', symbol='AAPL', price='10', quantity='1', fees='0', date=day), TransactionService, 'add_transaction'),
        'edit_trade': (f'/transactions/edit/{transaction}', dict(edit_price='10', edit_quantity='1', edit_fees='0', edit_date=day), TransactionService, 'update_transaction'),
        'delete_trade': (f'/transactions/delete/{transaction}', {}, TransactionService, 'delete_transaction'),
        'dividend': ('/transactions/dividends/add', dict(portfolio_id=portfolio, div_symbol='AAPL', amount='10', date=day), TransactionService, 'add_dividend'),
        'edit_dividend': (f'/transactions/dividends/edit/{dividend}', dict(edit_amount='10', edit_date=day), TransactionService, 'update_dividend'),
        'delete_dividend': (f'/transactions/dividends/delete/{dividend}', {}, TransactionService, 'delete_dividend'),
        'symbol': ('/transactions/symbols/add', dict(symbol_portfolio_id=portfolio, symbol_ticker='MSFT'), TransactionService, 'add_symbol'),
        'delete_symbol': ('/transactions/symbols/delete', dict(delete_symbol_portfolio_id=portfolio, delete_symbol_ticker='AAPL'), TransactionService, 'delete_symbol'),
        'portfolio': ('/portfolios/add', dict(name='New'), PortfolioService, 'create_portfolio'),
        'rename': (f'/portfolios/rename/{portfolio}', dict(name='New'), PortfolioService, 'rename_portfolio'),
        'delete_portfolio': (f'/portfolios/delete/{portfolio}', {}, PortfolioService, 'delete_portfolio'),
        'deposit': (f'/portfolios/deposit/{portfolio}', dict(amount_delta='10', deposit_date=day), PortfolioService, 'deposit_funds'),
        'withdraw': (f'/portfolios/withdraw/{portfolio}', dict(amount_delta='10', withdraw_date=day), PortfolioService, 'withdraw_funds'),
        'edit_event': (f'/portfolios/events/edit/{event}', dict(edit_cash_event_amount='5000', date=day), PortfolioService, 'update_portfolio_event'),
        'delete_event': (f'/portfolios/events/delete/{event}', {}, PortfolioService, 'delete_portfolio_event'),
        'transfer': ('/portfolios/transfers/add', dict(source_portfolio_id=portfolio, destination_portfolio_id=other, amount='10', date=day), TransferService, 'create'),
        'edit_transfer': ('/portfolios/transfers/edit/123', dict(source_portfolio_id=portfolio, destination_portfolio_id=other, amount='10', date=day), TransferService, 'update'),
        'delete_transfer': ('/portfolios/transfers/delete/123', {}, TransferService, 'delete'),
    }


CASES = ['buy', 'edit_trade', 'delete_trade', 'dividend', 'edit_dividend', 'delete_dividend', 'symbol', 'delete_symbol', 'portfolio', 'rename', 'delete_portfolio', 'deposit', 'withdraw', 'edit_event', 'delete_event', 'transfer', 'edit_transfer', 'delete_transfer']


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('unexpected', [False, True])
def test_service_failures_are_general_without_message_matching(forms, monkeypatch, case, unexpected):
    client, _, cases = forms
    path, data, service, method = cases[case]
    message = 'An account state rule with previously unseen wording.'
    called = []
    def fail(*args, **kwargs):
        called.append(True)
        if unexpected:
            raise RuntimeError('internal secret detail')
        raise ValueError(message)
    monkeypatch.setattr(service, method, fail)
    response = client.post(path, data=data, headers=HEADERS)
    assert called
    assert response.status_code == 400
    assert set(response.json['errors']) == {'__all__'}
    if unexpected:
        assert 'internal secret detail' not in response.get_data(as_text=True)
    else:
        assert response.json['errors']['__all__'] == message


@pytest.mark.parametrize('case,field,value', [
    ('buy', 'price', 'bad'), ('buy', 'quantity', '0'), ('buy', 'date', 'bad'),
    ('edit_trade', 'edit_quantity', '-1'), ('edit_trade', 'edit_fees', '-1'),
    ('dividend', 'amount', ''), ('edit_dividend', 'edit_date', 'bad'),
    ('symbol', 'symbol_ticker', ''), ('portfolio', 'name', ''), ('rename', 'name', ''),
    ('deposit', 'amount_delta', 'not-money'), ('withdraw', 'withdraw_date', 'bad'),
    ('edit_event', 'edit_cash_event_amount', '0'), ('transfer', 'amount', '-1'),
    ('edit_transfer', 'date', 'bad'),
])
def test_intrinsic_errors_mark_only_the_responsible_field(forms, case, field, value):
    client, _, cases = forms
    path, data, _, _ = cases[case]
    response = client.post(path, data={**data, field: value}, headers=HEADERS)
    assert response.status_code == 400
    assert set(response.json['errors']) == {field}


@pytest.mark.parametrize('type,price,quantity,fees,key', [
    ('Buy', '99999', '1', '0', 'PURCHASE_EXCEEDS_CASH'),
    ('Sell', '1', '11', '0', 'INSUFFICIENT_QUANTITY'),
    ('Sell', '1', '1', '2', 'FEES_EXCEED_PROCEEDS'),
])
def test_real_financial_rejections_preserve_history(forms, app, type, price, quantity, fees, key):
    client, _, cases = forms
    path, data, _, _ = cases['buy']
    response = client.post(path, data={**data, 'transaction_type': type, 'price': price, 'quantity': quantity, 'fees': fees}, headers=HEADERS)
    assert response.json['errors'] == {'__all__': MESSAGES[key]}
    with app.app_context():
        assert Transaction.query.count() == 1
        assert Transaction.query.one().quantity == Decimal('10')


def test_real_dividend_cash_history_failure_is_general(forms, app):
    client, uid, cases = forms
    portfolio_id = cases['buy'][1]['portfolio_id']
    with app.app_context():
        Services(user_id=uid).portfolio_service.withdraw_funds(portfolio_id, Decimal('4075'), date=datetime(2024, 1, 5))
    path, data, _, _ = cases['edit_dividend']
    response = client.post(path, data={**data, 'edit_amount': '1'}, headers=HEADERS)
    assert response.json['errors'] == {'__all__': MESSAGES['CASH_ALREADY_SPENT']}


def test_stale_and_forged_submissions_remain_general(forms, app):
    client, uid, cases = forms
    client.auto_mutation_tokens = False
    with app.test_request_context():
        token = issue_mutation_token(uid)
    with app.app_context():
        Services(user_id=uid).portfolio_service.create_portfolio('Revision change', user_id=uid)
    path, data, _, _ = cases['edit_trade']
    for intent in (token, 'forged'):
        response = client.post(path, data={**data, 'mutation_token': intent}, headers=HEADERS)
        assert response.status_code == 409
        assert set(response.json['errors']) == {'__all__'}


def test_account_deletion_format_and_state_have_distinct_placement(forms, app):
    client, uid, _ = forms
    response = client.post('/settings/delete/verify', data={'code': ''}, follow_redirects=True)
    markup = Markup(response.get_data(as_text=True))
    assert markup.by_id('delete-code')['aria-describedby'] == 'delete-code-error'
    assert 'hidden' not in markup.by_id('delete-code-error')
    response = client.post('/settings/delete/verify', data={'code': '123456'}, follow_redirects=True)
    markup = Markup(response.get_data(as_text=True))
    assert 'aria-invalid' not in markup.by_id('delete-code')
    summaries = [a for _, a in markup.nodes if 'data-form-error' in a and 'hidden' not in a]
    assert len(summaries) == 1
    with app.app_context():
        assert db.session.get(User, uid) is not None


def test_email_account_state_failure_is_general(forms):
    client, _, _ = forms
    with client.session_transaction() as state:
        mark_recent_auth(state)
    response = client.post('/update-email', data={'email': 'form_feedback@example.com'})
    markup = Markup(response.get_data(as_text=True))
    assert 'aria-invalid' not in markup.by_id('email')
    assert any('data-form-error' in a and 'hidden' not in a for _, a in markup.nodes)


def test_no_financial_message_to_field_maps_remain():
    for path in (Path('portfolio_app/routes/transactions.py'), Path('portfolio_app/routes/portfolios.py'), Path('portfolio_app/utils/http.py')):
        source = path.read_text(encoding='utf-8')
        assert 'field_error_response' not in source
        assert '_FIELD_MAP' not in source


def test_transfer_failed_post_preserves_field_placement_and_raw_values(forms):
    client, _, cases = forms
    path, data, _, _ = cases['transfer']
    response = client.post(path, data={**data, 'amount': '-0.123456789', 'date': 'bad-date'})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    markup = Markup(html)
    assert markup.by_id('transfer_amount')['value'] == '-0.123456789'
    assert markup.by_id('transfer_amount')['aria-describedby'] == 'transfer_amount-error'
    assert markup.by_id('transfer_date')['value'] == 'bad-date'
    assert markup.by_id('transfer_date')['aria-invalid'] == 'true'
    assert 'data-restored-transfer' in markup.by_id('transferForm')
    assert not any('data-form-error' in a and 'hidden' not in a for _, a in markup.nodes)
