"""Read-only preview arithmetic, ownership, resource and HTTP contracts."""
import re
import json
import random
import subprocess
from datetime import datetime
from decimal import Decimal, localcontext

import pytest
from flask import g, has_app_context
from sqlalchemy import select

from portfolio_app import create_app, db, limiter
from portfolio_app.models.user import User
from portfolio_app.models import Transaction
from portfolio_app.calculators.financial_math import transaction_cash_effect
from portfolio_app.services.transaction_preview import preview_values, render_preview
from tests.conftest import TestConfig
from tests._auth import authenticate_client
from tests.test_financial_baseline import ledger, _historical_trade


def payload():
    return dict(mode='create', transaction_type='Buy', price='10', quantity='2', fees='')


def client_for(app, uid):
    if has_app_context():
        g.pop('_login_user', None)
        g.pop('_services', None)
    client = app.test_client()
    client.auto_mutation_tokens = False  # Preview is a read, not a signed mutation.
    authenticate_client(client, uid)
    return client


@pytest.mark.parametrize('kind,fees,expected', [
    ('Buy', '', '20'), ('Buy', '0.005', '20.005'),
    ('Sell', '', '20'), ('Sell', '0.005', '19.995'), ('Sell', '20', '0'),
])
def test_preview_fee_semantics_and_rounding(app, ledger, kind, fees, expected):
    data = payload()
    data.update(transaction_type=kind, fees=fees)
    response = client_for(app, ledger.uid).post('/transactions/preview', json=data)
    assert response.status_code == 200
    assert response.json['amount'] == expected
    assert response.json['formatted_amount'] == ('0.00' if expected == '0' else '20.01' if expected == '20.005' else '20.00')
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('kind', ['Buy', 'Sell'])
def test_preview_matches_authoritative_exact_cash_effect(app, ledger, kind):
    row = _historical_trade(ledger, kind, '1234567890.123456789012345678901',
                            '.0000000001234567890123456789', 1, fees='.000000000000000000001')
    data = payload()
    data.update(mode='edit', transaction_id=str(row.id), price='', quantity='', fees='', transaction_type='ignored')
    with localcontext() as context:
        context.prec = 6
        expected = transaction_cash_effect(row)
        if kind == 'Buy': expected = expected.copy_negate()
        response = client_for(app, ledger.uid).post('/transactions/preview', json=data)
    assert response.status_code == 200
    assert Decimal(response.json['amount']) == expected
    assert response.json['transaction_type'] == kind


def test_edit_blank_fees_read_current_owned_record_without_mutating(app, ledger):
    row = _historical_trade(ledger, 'Buy', '10', '2', 1, fees='3.00000000000000001')
    def snapshot():
        return {table.name: list(db.session.execute(select(table))) for table in db.metadata.sorted_tables}
    data = payload()
    data.update(mode='edit', transaction_id=str(row.id), stored_fees='999')
    before = snapshot()
    client = client_for(app, ledger.uid)
    response = client.post('/transactions/preview', json=data)
    assert response.json['amount'] == '23.00000000000000001'
    assert snapshot() == before
    row.fees = Decimal('4.00000000000000002')
    db.session.commit()
    before = snapshot()
    assert client.post('/transactions/preview', json=data).json['amount'] == '24.00000000000000002'
    assert snapshot() == before
    data['fees'] = '0'
    assert client.post('/transactions/preview', json=data).json['amount'] == '20'


@pytest.mark.parametrize('mode', ['edit', 'retained'])
def test_preview_ownership_and_authentication(app, ledger, mode):
    row = _historical_trade(ledger, 'Buy', '10', '2', 1)
    other = User(username='preview-other', email='preview-other@example.com', is_verified=True)
    db.session.add(other)
    db.session.commit()
    data = payload()
    data.update(mode=mode, transaction_id=str(row.id), fees='')
    assert app.test_client().post('/transactions/preview', json=data).status_code == 302
    foreign = client_for(app, other.id).post('/transactions/preview', json=data)
    data['transaction_id'] = '99999999'
    missing = client_for(app, other.id).post('/transactions/preview', json=data)
    assert foreign.status_code == missing.status_code == 400
    assert foreign.json == missing.json == {'success': False, 'error': 'Preview unavailable.'}
    for identifier in ['9223372036854775807', '9223372036854775808', '9' * 100]:
        data['transaction_id'] = identifier
        response = client_for(app, other.id).post('/transactions/preview', json=data)
        assert response.status_code == 400
        assert response.json == missing.json
    assert client_for(app, ledger.uid).get('/transactions/preview').status_code == 405


@pytest.mark.parametrize('change', [
    {'price': ''}, {'price': '.'}, {'price': '1x2'},
    {'price': 'NaN'}, {'price': 'Infinity'},
    {'price': 1.25}, {'fees': None}, {'mode': 'bad'},
    {'transaction_type': 'Dividend'},
    {'price': '1' * 4097}, {'price': '1e999999'}, {'quantity': '1e-999999'},
    {'price': '1e4100', 'quantity': '1e4100'}, {'mode': 'edit', 'transaction_id': []},
    {'price': '1e64'}, {'quantity': '1e-65'},
])
def test_preview_rejects_invalid_or_unbounded_work(app, ledger, change):
    data = payload()
    data.update(change)
    response = client_for(app, ledger.uid).post('/transactions/preview', json=data)
    assert response.status_code == 400
    assert response.json == {'success': False, 'error': 'Preview unavailable.'}


def test_preview_legacy_syntax_tiny_decimals_and_body_limits(app, ledger):
    client = client_for(app, ledger.uid)
    data = payload()
    data.update(price=' +1,000.00100 ', quantity='1e-64')
    response = client.post('/transactions/preview', json=data)
    assert response.status_code == 200
    assert Decimal(response.json['amount']) == Decimal('1.000001e-61')
    assert response.json['formatted_amount'] == '0.00'
    assert client.post('/transactions/preview', data='{' + ' ' * 16384, content_type='application/json').status_code == 413
    assert client.post('/transactions/preview', data='{broken', content_type='application/json').status_code == 400
    assert client.post('/transactions/preview', json=[]).status_code == 400
    assert client.post('/transactions/preview', data=data).status_code == 400


def test_preview_requires_csrf_even_though_it_is_read_only(app, ledger, monkeypatch):
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    client = client_for(app, ledger.uid)
    assert client.post('/transactions/preview', json=payload()).status_code == 400
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/transactions/').text)[1]
    assert client.post('/transactions/preview', json=payload(), headers={'X-CSRFToken': 'forged'}).status_code == 400
    assert client.post('/transactions/preview', json=payload(), headers={'X-CSRFToken': token}).status_code == 200


def test_only_preview_is_excluded_from_financial_mutation_wrapper(app):
    for rule in app.url_map.iter_rules():
        if 'POST' in rule.methods and rule.endpoint.startswith(('transactions.', 'portfolios.')):
            protected = getattr(app.view_functions[rule.endpoint], '_protected_submission', False)
            assert protected == (rule.endpoint != 'transactions.transaction_preview')


def test_retained_fees_are_owned_current_read_only_and_csrf_protected(app, ledger, monkeypatch):
    row = _historical_trade(ledger, 'Sell', '1', '1', 1, fees='3.00000000000000001')
    client = client_for(app, ledger.uid)
    data = {'mode': 'retained', 'transaction_id': str(row.id), 'fees': '999'}
    def snapshot():
        return {table.name: list(db.session.execute(select(table))) for table in db.metadata.sorted_tables}
    before = snapshot()
    response = client.post('/transactions/preview', json=data)
    assert response.json == {'success': True, 'fees': '3.00000000000000001'}
    assert snapshot() == before
    row.fees = Decimal('4.005')
    db.session.commit()
    assert client.post('/transactions/preview', json=data).json['fees'] == '4.005'
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert client.post('/transactions/preview', json=data).status_code == 400
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/transactions/').text)[1]
    assert client.post('/transactions/preview', json=data, headers={'X-CSRFToken': token}).status_code == 200


@pytest.mark.parametrize('price,quantity,fees,expected', [
    ('1', '1', '3', '-2.00'), ('1', '1', '1', '0.00'),
    ('1', '1', '0', '1.00'), ('0', '1', '3', '-3.00'),
    ('1', '0', '0', '0.00'), ('1', '1', '1.005', '-0.01'),
    ('1', '1', '1.004999999999999999999999', '-0.00'),
])
def test_preview_arithmetic_does_not_enforce_transaction_acceptance(app, ledger, price, quantity, fees, expected):
    data = dict(mode='create', transaction_type='Sell', price=price, quantity=quantity, fees=fees)
    response = client_for(app, ledger.uid).post('/transactions/preview', json=data)
    assert response.status_code == 200
    assert response.json['formatted_amount'] == expected


def test_production_bigint_preview_matches_python_exact_calculator_and_formatting():
    # One Node process, real production functions, deterministic varied decimal
    # vectors. No copied JS arithmetic oracle and no binary floating point.
    operands = [
        ('1', '1', '3'), ('1', '1', '1'), ('0', '1', '0'),
        ('-1', '1', '0'), ('1', '-1', '-2'), ('-0.00', '2', '0'),
        ('1.005', '1', '0'), ('1.004999999999999999999999', '1', '0'),
        ('1', '1', '1.005'), ('1', '1', '1.004999999999999999999999'),
        ('999999999999999999.995', '1', '.005'),
        # Exercise the new entry boundaries; derived products can exceed them.
        ('0.' + '0' * 63 + '1', '0.0001', '0'),
        (' +1,000.00100 ', '1e-64', '.1'),
        ('1234567890.123456789012345678901', '.0000000001234567890123456789', '.000000000000000000001'),
        ('9' * 64, '1e-60', '.005'),
    ]
    rng = random.Random(10714)
    for _ in range(150):
        operands.append(tuple(
            f"{rng.choice(('', '-'))}{rng.randrange(10**40)}e{rng.randrange(-60, 25)}"
            for _ in range(3)
        ))
    vectors = [[kind, *values] for values in operands for kind in ('Buy', 'Sell')]
    result = subprocess.run(['node', 'tests/transaction_previews.js', '--calculate'],
                            input=json.dumps(vectors), text=True, capture_output=True, check=True, timeout=30)
    actual = json.loads(result.stdout)
    assert len(actual) == len(vectors)
    for vector, calculated in zip(vectors, actual):
        kind, price, quantity, fees = vector
        expected = render_preview(kind, preview_values(dict(price=price, quantity=quantity, fees=fees)))
        assert calculated is not None, vector
        assert Decimal(calculated['amount']) == Decimal(expected['amount']), vector
        assert calculated['formatted_amount'] == expected['formatted_amount'], vector


def test_preview_rate_limit_is_per_authenticated_user(tmp_path):
    class Limited(TestConfig):
        RATELIMIT_ENABLED = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'preview-limit.sqlite').as_posix()}"
    application = create_app(Limited)
    with application.app_context():
        users = [User(username=f'preview-{i}', email=f'preview-{i}@example.com', is_verified=True) for i in range(2)]
        db.session.add_all(users)
        db.session.commit()
        ids = [user.id for user in users]
    limiter.reset()
    try:
        client = client_for(application, ids[0])
        for _ in range(120):
            assert client.post('/transactions/preview', json=payload()).status_code == 200
        assert client.post('/transactions/preview', json=payload()).status_code == 429
        assert client_for(application, ids[1]).post('/transactions/preview', json=payload()).status_code == 200
    finally:
        limiter.reset()


def test_all_twelve_financial_inputs_are_explicit(app, ledger):
    from html.parser import HTMLParser
    class Inputs(HTMLParser):
        def __init__(self, text):
            super().__init__()
            self.fields = []
            self.feed(text)
        def handle_starttag(self, tag, attrs):
            if tag == 'input': self.fields.append(dict(attrs))
    client = client_for(app, ledger.uid)
    expected = {
        '/transactions/': {'price', 'quantity', 'fees', 'edit_price', 'edit_quantity', 'edit_fees', 'add_div_amount', 'edit_amount'},
        '/portfolios/': {'add_funds_amount', 'withdraw_funds_amount', 'edit_cash_event_amount', 'transfer_amount'},
    }
    for route, ids in expected.items():
        response = client.get(route)
        assert response.status_code == 200
        inputs = Inputs(response.text).fields
        fields = [field for field in inputs if field.get('data-numeric') == 'decimal']
        assert {field['id'] for field in fields} == ids
        assert all(field['type'] == 'text' and field['inputmode'] == 'decimal' for field in fields)
        assert not [field for field in inputs if field.get('inputmode') == 'decimal' and 'data-numeric' not in field]


def test_final_submission_preserves_blank_fee_semantics_and_ignores_preview_amount(app, ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, Decimal('100'), date=datetime(2024, 1, 1))
    row = ledger.svc.transaction_service.add_transaction(
        ledger.pid, 'Buy', 'BTC', Decimal('1.00000000000000001'), Decimal('2'),
        Decimal('3.00000000000000003'), date=datetime(2024, 1, 2),
    )
    identifier = row.id
    client = app.test_client()  # Normal signed mutation intents, unlike preview reads.
    authenticate_client(client, ledger.uid)
    headers = {'X-Requested-With': 'XMLHttpRequest'}
    response = client.post(f'/transactions/edit/{identifier}', headers=headers, data={
        'edit_price': ' +1.00000000000000001 ', 'edit_quantity': '2e0',
        'edit_fees': '', 'edit_notes': 'retained fee', 'preview_amount': '999',
    })
    assert response.json['success'], response.json
    db.session.expire_all()
    saved = db.session.get(Transaction, identifier)
    assert (saved.price, saved.quantity, saved.fees) == (
        Decimal('1.00000000000000001'), Decimal('2'), Decimal('3.00000000000000003'),
    )
    assert transaction_cash_effect(saved) == Decimal('-5.00000000000000005')
    response = client.post('/transactions/add', headers=headers, data={
        'portfolio_id': str(ledger.pid), 'transaction_type': 'Buy', 'symbol': 'BTC',
        'price': '1.00000000000000001', 'quantity': '0.00000000000000002',
        'fees': '', 'date': '2024-01-03', 'preview_amount': '999',
    })
    assert response.json['success'], response.json
    db.session.expire_all()
    created = ledger.svc.transaction_repo.get_by_portfolio_id(ledger.pid)[-1]
    assert created.id != identifier
    assert created.fees == Decimal('0')
    assert transaction_cash_effect(created) == Decimal('-0.0000000000000000200000000000000002')
