from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import re

import pytest

from config import Config
from portfolio_app import create_app, db
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{(Path(__file__).resolve().parent / 'test_assets.db').as_posix()}"
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


def _seed_user(username='asset_user'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _visible_text(html):
    parser = _VisibleTextParser()
    parser.feed(html)
    return '\n'.join(parser.parts)


def _seed_asset_with_activity(uid):
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio('Growth', user_id=uid)
    svc.portfolio_service.deposit_funds(portfolio.id, _dec('5000'), date=datetime(2024, 1, 1))
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Buy',
        symbol='AAPL',
        price=_dec('100'),
        quantity=_dec('10'),
        fees=_dec('0'),
        notes='Buy note',
        date=datetime(2024, 1, 2),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Sell',
        symbol='AAPL',
        price=_dec('120'),
        quantity=_dec('5'),
        fees=_dec('0'),
        notes='بيع جزئي',
        date=datetime(2024, 1, 3),
    )
    svc.transaction_service.add_dividend(
        portfolio_id=portfolio.id,
        symbol='AAPL',
        amount=_dec('75'),
        date=datetime(2024, 1, 4),
        notes='دخل عربي',
    )
    return portfolio.id


def test_assets_page_uses_asset_terminology_and_total_buy_cost(app):
    with app.app_context():
        uid = _seed_user()
        portfolio_id = _seed_asset_with_activity(uid)
        summary = PortfolioCalculator.get_symbol_transactions_summary(portfolio_id, 'AAPL', user_id=uid)
        assert summary['total_buy_cost'] == _dec('1000.0000000000')
        assert summary['cost_basis'] == _dec('500.0000000000')

    client = app.test_client()
    _login(client, uid)
    response = client.get('/transactions/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    text = _visible_text(html)

    for label in (
        'Assets', 'Add Asset', 'ENTRIES',
        'TOTAL BUY COST', 'QUANTITY', 'AVERAGE COST',
        'REALIZED P&L', 'REALIZED RETURN', 'INCOME', 'Quantity', 'Fee',
        'Total', 'Realized P&L', 'Return', 'Income',
    ):
        assert label in text
    assert 'placeholder="Search asset..."' in html

    for old_label in (
        'Transactions', 'Add Symbol',
        'TRANSACTIONS', 'TOTAL SPENT', 'Total Spent',
        'HOLDINGS', 'AVG COST', 'TOTAL DIVIDENDS',
        'Qty', 'Fees', 'Total Amount', 'P&L(%)',
        'Dividend',
    ):
        assert old_label not in text
    assert 'Search symbol...' not in html

    assert re.search(r'REALIZED P&L\s+\+100\.00\s+REALIZED RETURN\s+\+17\.50%', text)
    assert not re.search(r'REALIZED P&L\s+\+100\.00\s+\+10\.00%', text)
    assert '1,000.00' in text
    assert '500.00' not in text
    assert 'بيع جزئي' in text
    assert 'دخل عربي' in text


def test_asset_entry_and_income_financial_behavior_is_unchanged(app):
    with app.app_context():
        uid = _seed_user('asset_financial')
        portfolio_id = _seed_asset_with_activity(uid)

        tx_summary = PortfolioCalculator.get_symbol_transactions_summary(
            portfolio_id, 'AAPL', user_id=uid,
        )
        performance = PortfolioCalculator.get_realized_performance_for_portfolio(
            portfolio_id, user_id=uid,
        )
        cash = PortfolioCalculator.get_available_cash_for_portfolio(portfolio_id, user_id=uid)

        assert tx_summary['realized_pnl'] == _dec('100.0000000000')
        assert tx_summary['cost_basis'] == _dec('500.0000000000')
        assert performance['total_income'] == _dec('75.0000000000')
        assert performance['realized_pnl'] == _dec('100.0000000000')
        assert performance['return_amount'] == _dec('175.0000000000')
        assert 'total_dividends' not in performance
        assert 'return_numerator' not in performance
        assert cash == _dec('4675.0000000000')


def test_assets_routes_keep_existing_urls_and_return_new_messages(app):
    with app.app_context():
        uid = _seed_user('asset_routes')
        svc = Services(user_id=uid)
        portfolio = svc.portfolio_service.create_portfolio('Routes', user_id=uid)
        svc.portfolio_service.deposit_funds(portfolio.id, _dec('1000'), date=datetime(2024, 1, 1))
        portfolio_id = portfolio.id

    client = app.test_client()
    _login(client, uid)

    add_asset = client.post(
        '/transactions/symbols/add',
        data={'symbol_portfolio_id': str(portfolio_id), 'symbol_ticker': 'MSFT'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    add_entry = client.post(
        '/transactions/add',
        data={
            'portfolio_id': str(portfolio_id),
            'transaction_type': 'Buy',
            'symbol': 'MSFT',
            'price': '10',
            'quantity': '5',
            'fees': '0',
            'date': '2024-01-02',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    add_income = client.post(
        '/transactions/dividends/add',
        data={
            'portfolio_id': str(portfolio_id),
            'div_symbol': 'MSFT',
            'amount': '12.50',
            'date': '2024-01-03',
            'notes': 'دخل',
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert add_asset.status_code == 200
    assert add_asset.get_json()['message'] == "'MSFT' asset added to portfolio."
    assert add_entry.status_code == 200
    assert add_entry.get_json()['message'] == 'Asset entry added.'
    assert add_income.status_code == 200
    assert add_income.get_json()['message'] == 'Income added.'
