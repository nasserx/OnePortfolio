from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
import re
from urllib.parse import quote_plus

from portfolio_app import db
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


def _dec(value):
    return Decimal(str(value))


def _seed_user(username='overview_user'):
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


def _portfolio_card_text(html):
    match = re.search(
        r'<article class="[^"]*overview-portfolio-card[^"]*".*?</article>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return _visible_text(match.group(0))


def _seed_overview_activity(uid):
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio('النمو Growth', user_id=uid)
    svc.portfolio_service.deposit_funds(
        portfolio.id, _dec('10000'), date=datetime(2024, 1, 1),
    )
    svc.portfolio_service.withdraw_funds(
        portfolio.id, _dec('1500'), date=datetime(2024, 1, 2),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Buy',
        symbol='AAPL',
        price=_dec('100'),
        quantity=_dec('20'),
        fees=_dec('0'),
        date=datetime(2024, 1, 3),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Sell',
        symbol='AAPL',
        price=_dec('120'),
        quantity=_dec('5'),
        fees=_dec('0'),
        date=datetime(2024, 1, 4),
    )
    svc.transaction_service.add_dividend(
        portfolio_id=portfolio.id,
        symbol='AAPL',
        amount=_dec('75'),
        date=datetime(2024, 1, 5),
        notes='دخل',
    )
    return portfolio


def test_overview_uses_current_health_metrics_and_terminology(app):
    with app.app_context():
        uid = _seed_user()
        portfolio = _seed_overview_activity(uid)

        summary, _ = PortfolioCalculator.get_portfolio_summary(user_id=uid)
        item = summary[0]
        totals = PortfolioCalculator.get_portfolio_dashboard_totals(user_id=uid)

        assert item['total_capital'] == _dec('8500.00')
        assert item['cash'] == _dec('7175.0000000000')
        assert item['positions'] == _dec('1500.0000000000')
        assert item['book_value'] == _dec('8675.0000000000')
        assert item['total_income'] == _dec('75.0000000000')
        assert item['realized_pnl'] == _dec('100.0000000000')
        assert item['return_amount'] == _dec('175.0000000000')
        assert item['return_display'] == '+1.75%'

        assert totals['total_capital'] == _dec('8500.00')
        assert totals['total_cash'] == _dec('7175.0000000000')
        assert totals['total_positions'] == _dec('1500.0000000000')
        assert totals['total_value'] == _dec('8675.0000000000')
        assert totals['total_income'] == _dec('75.0000000000')
        assert totals['realized_pnl'] == _dec('100.0000000000')
        assert totals['return_amount'] == _dec('175.0000000000')
        assert totals['return_display'] == '+1.75%'
        assert 'total_realized_pnl' not in totals
        assert 'realized_roi_display' not in totals

    client = app.test_client()
    _login(client, uid)
    response = client.get('/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    text = _visible_text(html)
    card_text = _portfolio_card_text(html)

    for label in (
        'TOTAL CAPITAL',
        'TOTAL CASH',
        'BOOK VALUE',
        'TOTAL INCOME',
        'REALIZED P&L',
    ):
        assert label in text

    for label in (
        'BOOK VALUE',
        'RETURN',
        'REALIZED P&L',
        'INCOME',
    ):
        assert label in card_text

    for removed_card_label in (
        'TOTAL CAPITAL',
        'TOTAL CASH',
        'POSITIONS',
        'TOTAL INCOME',
    ):
        assert removed_card_label not in card_text

    assert 'View Assets' in text

    for old_label in (
        'TOTAL CONTRIBUTED',
        'Total Contributed',
        'TOTAL DIVIDENDS',
        'Total Dividends',
        'COST BASIS',
        'Cost Basis',
        'DIVIDENDS',
        'Dividends',
        'View Transactions',
        'ALLOCATION',
        'Allocation',
        'MARKET VALUE',
        'Market Value',
        'UNREALIZED P&L',
        'Unrealized P&L',
    ):
        assert old_label not in text

    assert 'النمو Growth' in text
    assert '8,500.00' in text
    assert '7,175.00' in text
    assert '8,675.00' in card_text
    assert '+75.00' in card_text
    assert '+100.00' in card_text
    assert '+1.75%' in card_text
    assert f'href="/transactions/?portfolio={quote_plus(portfolio.name)}"' in html
