"""Financial and ownership invariants for whole-symbol deletion."""

from datetime import datetime
from decimal import Decimal

import pytest

from portfolio_app import db
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models import Dividend, Symbol, Transaction
from portfolio_app.models.user import User
from tests._auth import authenticate_client
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES


def _dec(value):
    return Decimal(str(value))


def _seed_user(username):
    user = User(
        username=username,
        email=f'{username}@example.com',
        is_verified=True,
    )
    user.password_hash = 'legacy-test-hash'
    db.session.add(user)
    db.session.commit()
    return user.id


def _create_portfolio(user_id, name='Portfolio', deposit='1000'):
    svc = Services(user_id=user_id)
    portfolio = svc.portfolio_service.create_portfolio(name, user_id=user_id)
    svc.portfolio_service.deposit_funds(
        portfolio.id, _dec(deposit), date=datetime(2026, 1, 1),
    )
    return svc, portfolio


def _add_transaction(svc, portfolio_id, transaction_type, symbol, price, quantity='1'):
    return svc.transaction_service.add_transaction(
        portfolio_id=portfolio_id,
        transaction_type=transaction_type,
        symbol=symbol,
        price=_dec(price),
        quantity=_dec(quantity),
        fees=_dec('0'),
        date=datetime(2026, 1, 2),
    )


def test_symbol_delete_rejects_negative_prospective_cash_without_partial_deletion(app):
    with app.app_context():
        user_id = _seed_user('cash_guard')
        svc, portfolio = _create_portfolio(user_id, deposit='100')
        svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
        svc.transaction_service.add_symbol(portfolio.id, 'MSFT')

        _add_transaction(svc, portfolio.id, 'Buy', 'AAPL', '100')
        _add_transaction(svc, portfolio.id, 'Sell', 'AAPL', '200')
        _add_transaction(svc, portfolio.id, 'Buy', 'MSFT', '200')

        before_cash = PortfolioCalculator.get_available_cash_for_portfolio(
            portfolio.id, user_id=user_id,
        )
        before_transaction_ids = {
            row.id for row in svc.transaction_repo.get_by_portfolio_id(portfolio.id)
        }

        with pytest.raises(ValueError) as excinfo:
            svc.transaction_service.delete_symbol(portfolio.id, 'aapl')

        assert str(excinfo.value) == MESSAGES['CASH_ALREADY_SPENT']
        assert PortfolioCalculator.get_available_cash_for_portfolio(
            portfolio.id, user_id=user_id,
        ) == before_cash == _dec('0')
        assert {
            row.id for row in svc.transaction_repo.get_by_portfolio_id(portfolio.id)
        } == before_transaction_ids
        assert svc.symbol_repo.get_by_portfolio_and_ticker(portfolio.id, 'AAPL') is not None


def test_rejected_symbol_delete_preserves_symbol_transactions_and_income(app):
    with app.app_context():
        user_id = _seed_user('atomic_reject')
        svc, portfolio = _create_portfolio(user_id, deposit='100')
        symbol = svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
        svc.transaction_service.add_symbol(portfolio.id, 'MSFT')
        buy = _add_transaction(svc, portfolio.id, 'Buy', 'AAPL', '100')
        sell = _add_transaction(svc, portfolio.id, 'Sell', 'AAPL', '200')
        dividend = svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('10'), datetime(2026, 1, 3),
        )
        _add_transaction(svc, portfolio.id, 'Buy', 'MSFT', '210')

        with pytest.raises(ValueError) as excinfo:
            svc.transaction_service.delete_symbol(portfolio.id, 'AAPL')

        assert str(excinfo.value) == MESSAGES['CASH_ALREADY_SPENT']
        assert db.session.get(Symbol, symbol.id) is not None
        assert db.session.get(Transaction, buy.id) is not None
        assert db.session.get(Transaction, sell.id) is not None
        assert db.session.get(Dividend, dividend.id) is not None


def test_valid_symbol_delete_removes_transactions_income_and_tracking_atomically(app):
    with app.app_context():
        user_id = _seed_user('valid_delete')
        svc, portfolio = _create_portfolio(user_id)
        aapl_symbol = svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
        svc.transaction_service.add_symbol(portfolio.id, 'MSFT')
        aapl_tx = _add_transaction(svc, portfolio.id, 'Buy', 'AAPL', '100')
        aapl_dividend = svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('25'), datetime(2026, 1, 3),
        )
        msft_tx = _add_transaction(svc, portfolio.id, 'Buy', 'MSFT', '50')
        msft_dividend = svc.transaction_service.add_dividend(
            portfolio.id, 'MSFT', _dec('5'), datetime(2026, 1, 3),
        )
        aapl_symbol_id = aapl_symbol.id
        aapl_tx_id = aapl_tx.id
        aapl_dividend_id = aapl_dividend.id
        msft_tx_id = msft_tx.id
        msft_dividend_id = msft_dividend.id

        svc.transaction_service.delete_symbol(portfolio.id, 'aapl')

        assert db.session.get(Symbol, aapl_symbol_id) is None
        assert db.session.get(Transaction, aapl_tx_id) is None
        assert db.session.get(Dividend, aapl_dividend_id) is None
        assert svc.symbol_repo.get_by_portfolio_and_ticker(portfolio.id, 'AAPL') is None
        assert db.session.get(Transaction, msft_tx_id) is not None
        assert db.session.get(Dividend, msft_dividend_id) is not None
        assert svc.symbol_repo.get_by_portfolio_and_ticker(portfolio.id, 'MSFT') is not None
        assert PortfolioCalculator.get_available_cash_for_portfolio(
            portfolio.id, user_id=user_id,
        ) == _dec('955')


def test_symbol_delete_is_tenant_scoped(app):
    with app.app_context():
        owner_id = _seed_user('symbol_owner')
        attacker_id = _seed_user('symbol_attacker')
        owner_svc, portfolio = _create_portfolio(owner_id)
        owner_svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
        transaction = _add_transaction(owner_svc, portfolio.id, 'Buy', 'AAPL', '100')
        dividend = owner_svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('25'), datetime(2026, 1, 3),
        )

        attacker_svc = Services(user_id=attacker_id)
        with pytest.raises(ValueError) as excinfo:
            attacker_svc.transaction_service.delete_symbol(portfolio.id, 'AAPL')

        assert str(excinfo.value) == MESSAGES['PORTFOLIO_NOT_FOUND']
        assert db.session.get(Transaction, transaction.id) is not None
        assert db.session.get(Dividend, dividend.id) is not None
        assert owner_svc.symbol_repo.get_by_portfolio_and_ticker(portfolio.id, 'AAPL') is not None


def test_assets_page_discloses_transaction_and_income_cascade_counts(app):
    with app.app_context():
        user_id = _seed_user('delete_copy')
        svc, portfolio = _create_portfolio(user_id)
        svc.transaction_service.add_symbol(portfolio.id, 'AAPL')
        _add_transaction(svc, portfolio.id, 'Buy', 'AAPL', '100')
        svc.transaction_service.add_dividend(
            portfolio.id, 'AAPL', _dec('25'), datetime(2026, 1, 3),
        )

    client = app.test_client()
    authenticate_client(client, user_id)

    response = client.get('/transactions/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-tx-count="1"' in html
    assert 'data-income-count="1"' in html
    assert "removalCounts.join(' and ')" in html
