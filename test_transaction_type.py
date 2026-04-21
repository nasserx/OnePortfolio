"""Tests for TransactionAddForm transaction_type defaulting behaviour."""

import pytest
from types import SimpleNamespace
from portfolio_app.forms.transaction_forms import TransactionAddForm
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


def test_default_buy_when_type_missing():
    f = _form()
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Buy'


def test_default_buy_when_type_empty():
    f = _form({'transaction_type': ''})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Buy'


def test_default_buy_when_type_invalid():
    f = _form({'transaction_type': 'INVALID'})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Buy'


def test_explicit_buy():
    f = _form({'transaction_type': 'Buy'})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Buy'


def test_explicit_sell():
    f = _form({'transaction_type': 'Sell'})
    assert f.validate()
    assert f.cleaned_data['transaction_type'] == 'Sell'


def test_default_matches_first_transaction_type_in_config():
    """Default must always equal Config.TRANSACTION_TYPES[0]."""
    f = _form()
    f.validate()
    assert f.cleaned_data['transaction_type'] == Config.TRANSACTION_TYPES[0]


def test_no_transaction_type_error_ever():
    """transaction_type should never appear in form errors."""
    for value in ('', None, 'GARBAGE', 'buy', 'SELL'):
        f = _form({'transaction_type': value})
        f.validate()
        assert 'transaction_type' not in f.errors
