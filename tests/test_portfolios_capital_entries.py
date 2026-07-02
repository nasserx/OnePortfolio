from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from config import Config
from portfolio_app import create_app, db
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from portfolio_app.utils.messages import MESSAGES


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_portfolios_capital.db').as_posix()}"
    )


@pytest.fixture
def app():
    app = create_app(_TestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


def _dec(value):
    return Decimal(str(value))


def _seed_user(username='capital_user'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def test_deposit_and_withdraw_create_capital_entries_and_update_accounting(app):
    with app.app_context():
        uid = _seed_user()
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Capital', user_id=uid)

        svc.portfolio_service.deposit_funds(
            portfolio.id, _dec('1000'), notes='Initial capital',
            date=datetime(2024, 1, 1),
        )
        svc.portfolio_service.withdraw_funds(
            portfolio.id, _dec('250'), notes='سحب نقدي',
            date=datetime(2024, 1, 2),
        )

        events = svc.portfolio_event_repo.get_by_portfolio_id(portfolio.id)
        assert [event.event_type for event in events] == ['Deposit', 'Withdrawal']
        assert [event.amount_delta for event in events] == [_dec('1000.00'), _dec('-250.00')]

        assert PortfolioCalculator.get_total_capital_for_portfolio(portfolio.id) == _dec('750.00')
        assert PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id) == _dec('750.00')

        performance = PortfolioCalculator.get_realized_performance_for_portfolio(portfolio.id)
        assert performance['realized_pnl'] == _dec('0')
        assert performance['total_dividends'] == _dec('0')


def test_portfolios_page_renders_capital_metrics_and_log(app):
    with app.app_context():
        uid = _seed_user('render_user')
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Long Term', user_id=uid)
        svc.portfolio_service.deposit_funds(
            portfolio.id, _dec('1000'), notes='Deposit note',
            date=datetime(2024, 1, 1),
        )
        svc.portfolio_service.withdraw_funds(
            portfolio.id, _dec('250'), notes='ملاحظة عربية',
            date=datetime(2024, 1, 2),
        )

    client = app.test_client()
    _login(client, uid)
    response = client.get('/portfolios/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'TOTAL CONTRIBUTED' not in html
    assert 'Total Contributed' not in html
    for label in (
        'CAPITAL ENTRIES', 'TOTAL CAPITAL', 'TOTAL CASH',
        'POSITIONS', 'BOOK VALUE', 'Date', 'Type', 'Amount',
        'Notes', 'Actions',
    ):
        assert label in html

    assert '>Deposit<' in html
    assert '>Withdraw<' in html
    assert '+1,000.00' in html
    assert '-250.00' in html
    assert 'Deposit to <span id="deposit_portfolio_title"></span>' in html
    assert 'Withdraw from <span id="withdraw_portfolio_title"></span>' in html
    assert 'Record Deposit' in html
    assert 'Record Withdraw' in html
    assert 'ملاحظة عربية' in html


def test_portfolio_routes_create_deposit_withdraw_and_recalculate_totals(app):
    with app.app_context():
        uid = _seed_user('route_user')
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Routes', user_id=uid)
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, uid)

    deposit_response = client.post(
        f'/portfolios/deposit/{portfolio_id}',
        data={
            'amount_delta': '1,000.00',
            'deposit_date': '2024-01-01',
            'notes': 'Route deposit',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    withdraw_response = client.post(
        f'/portfolios/withdraw/{portfolio_id}',
        data={
            'amount_delta': '250.00',
            'withdraw_date': '2024-01-02',
            'notes': 'Route withdraw',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert deposit_response.status_code == 200
    assert deposit_response.get_json()['success'] is True
    assert withdraw_response.status_code == 200
    assert withdraw_response.get_json()['success'] is True

    with app.app_context():
        assert PortfolioCalculator.get_total_capital_for_portfolio(portfolio_id, user_id=uid) == _dec('750.00')
        assert PortfolioCalculator.get_available_cash_for_portfolio(portfolio_id, user_id=uid) == _dec('750.00')


def test_withdraw_exceeding_cash_fails_with_clear_amount_error(app):
    with app.app_context():
        uid = _seed_user('overdraw_user')
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Overdraw', user_id=uid)
        svc.portfolio_service.deposit_funds(portfolio.id, _dec('100'), date=datetime(2024, 1, 1))
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, uid)
    response = client.post(
        f'/portfolios/withdraw/{portfolio_id}',
        data={'amount_delta': '101', 'withdraw_date': '2024-01-02'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert response.status_code == 400
    assert response.get_json()['errors']['amount_delta'] == MESSAGES['WITHDRAWAL_EXCEEDS_CASH']


def test_editing_and_deleting_capital_entries_update_summary(app):
    with app.app_context():
        uid = _seed_user('edit_delete_user')
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Edit Delete', user_id=uid)
        svc.portfolio_service.deposit_funds(portfolio.id, _dec('1000'), date=datetime(2024, 1, 1))
        svc.portfolio_service.withdraw_funds(portfolio.id, _dec('250'), date=datetime(2024, 1, 2))
        events = svc.portfolio_event_repo.get_by_portfolio_id(portfolio.id)
        deposit = next(event for event in events if event.event_type == 'Deposit')
        withdrawal = next(event for event in events if event.event_type == 'Withdrawal')

        svc.portfolio_service.update_portfolio_event(
            deposit.id, amount_delta=_dec('1200'), notes='Edited deposit',
            date=datetime(2024, 1, 3),
        )
        assert PortfolioCalculator.get_total_capital_for_portfolio(portfolio.id, user_id=uid) == _dec('950.00')
        assert PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id, user_id=uid) == _dec('950.00')

        svc.portfolio_service.delete_portfolio_event(withdrawal.id)
        assert PortfolioCalculator.get_total_capital_for_portfolio(portfolio.id, user_id=uid) == _dec('1200.00')
        assert PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id, user_id=uid) == _dec('1200.00')


def test_existing_portfolio_creation_and_listing_still_work(app):
    with app.app_context():
        uid = _seed_user('list_user')

    client = app.test_client()
    _login(client, uid)
    create_response = client.post(
        '/portfolios/add',
        data={'name': 'Listed'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    list_response = client.get('/portfolios/')

    assert create_response.status_code == 200
    assert create_response.get_json()['success'] is True
    assert list_response.status_code == 200
    assert 'Listed' in list_response.get_data(as_text=True)
