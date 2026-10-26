"""Reject unsupported transaction types without manufacturing a Buy."""

from types import SimpleNamespace
from datetime import datetime
from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.forms.transaction_forms import TransactionAddForm
from portfolio_app.models import Transaction
from tests.test_financial_baseline import ledger
from tests._auth import authenticate_client
from config import Config


VALID_PORTFOLIO_ID = 1
_portfolio = SimpleNamespace(id=VALID_PORTFOLIO_ID, name='Test')

BASE_DATA = {
    'portfolio_id': str(VALID_PORTFOLIO_ID),
    'symbol':       'AAPL',
    'price':        '150.00',
    'quantity':     '10',
    'date':         '2026-01-01',
}


def _form(overrides=None):
    data = {**BASE_DATA, **(overrides or {})}
    return TransactionAddForm(data, [_portfolio])


def test_rejects_missing_type():
    f = _form()
    assert not f.validate()
    assert 'transaction_type' in f.errors
    assert 'transaction_type' not in f.cleaned_data


@pytest.mark.parametrize('value', ['', None, '   ', 'INVALID', 'Dividend', 'buy', 'SELL'])
def test_rejects_unapproved_type(value):
    f = _form({'transaction_type': value})
    assert not f.validate()
    assert 'transaction_type' in f.errors
    assert 'transaction_type' not in f.cleaned_data


@pytest.mark.parametrize('value', Config.TRANSACTION_TYPES)
def test_accepts_approved_type(value):
    f = _form({'transaction_type': value})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == value


def test_preserves_existing_surrounding_whitespace_handling():
    f = _form({'transaction_type': ' Sell '})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Sell'


def _seed_owned_position(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'), date=datetime(2024, 1, 1))
    ledger.svc.transaction_service.add_transaction(
        ledger.pid, 'Buy', 'AAPL', D('100'), D('2'), D('0'), date=datetime(2024, 1, 2),
    )


def _financial_state(ledger):
    db.session.expire_all()
    return (
        PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid),
        PC.get_quantity_held_for_symbol(ledger.pid, 'AAPL', user_id=ledger.uid),
        tuple(db.session.execute(sa.select(Transaction.__table__).order_by(Transaction.id))),
    )


@pytest.mark.parametrize('value', [None, '', '   ', 'INVALID', 'Dividend', 'buy', 'SELL'])
def test_http_rejects_invalid_type_without_financial_changes(ledger, app, value):
    _seed_owned_position(ledger)
    before = _financial_state(ledger)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    data = dict(BASE_DATA, portfolio_id=str(ledger.pid), price='10', quantity='1')
    if value is not None:
        data['transaction_type'] = value
    response = client.post('/transactions/add', data=data, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert not response.json['success']
    assert 'transaction_type' in response.json['errors']
    assert _financial_state(ledger) == before
    assert before[0].cash_balance == D('800') and before[1] == D('2')


@pytest.mark.parametrize('value', [None, '', 'INVALID', 'Dividend', 'buy', 'SELL'])
def test_service_rejects_invalid_type_before_accounting(ledger, monkeypatch, value):
    _seed_owned_position(ledger)
    before = _financial_state(ledger)
    monkeypatch.setattr(ledger.svc.transaction_service.cash_account, 'validate',
                        lambda *a, **kw: pytest.fail('Invalid type reached cash accounting'))
    with pytest.raises(ValueError, match='Buy or Sell'):
        ledger.svc.transaction_service.add_transaction(
            ledger.pid, value, 'AAPL', D('10'), D('1'), D('0'), date=datetime(2024, 1, 3),
        )
    assert _financial_state(ledger) == before


@pytest.mark.parametrize('kind,cash,quantity', [('Buy', '790', '3'), ('Sell', '810', '1')])
def test_http_approved_types_keep_their_financial_meaning(ledger, app, kind, cash, quantity):
    _seed_owned_position(ledger)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.post('/transactions/add', data=dict(
        BASE_DATA, portfolio_id=str(ledger.pid), price='10', quantity='1', transaction_type=kind,
    ), headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.json['success']
    snapshot, held, rows = _financial_state(ledger)
    assert snapshot.cash_balance == D(cash)
    assert held == D(quantity)
    assert [row.transaction_type for row in rows] == ['Buy', kind]
