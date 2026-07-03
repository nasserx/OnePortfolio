from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
import json
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


def _portfolio_rows_text(html):
    start = html.index('data-overview-portfolio-rows')
    end = html.index('</section>', start)
    return _visible_text(html[start:end])


def _chart_data(html):
    match = re.search(r'const chartData = (\{.*?\});', html, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


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
    row_text = _portfolio_rows_text(html)
    chart_data = _chart_data(html)

    for label in (
        'TOTAL CAPITAL',
        'TOTAL CASH',
        'BOOK VALUE',
        'TOTAL INCOME',
        'REALIZED P&L',
    ):
        assert label in text

    for label in (
        'Portfolio',
        'Book Value',
        'Realized P&L',
        'Return',
        'Income',
        'Assets',
    ):
        assert label in row_text

    column_positions = [
        row_text.index(label)
        for label in ('Portfolio', 'Book Value', 'Income', 'Realized P&L', 'Return', 'Assets')
    ]
    assert column_positions == sorted(column_positions)
    assert 'class="overview-portfolio-marker allocation-marker-1"' in html
    assert '>ا</span>' in html

    assert 'By Book Value' in text
    assert 'By Capital' in text
    assert html.count('<canvas') == 2
    assert '<canvas id="bookValueChart"' in html
    assert '<canvas id="bookCapitalChart"' in html
    assert set(chart_data) == {'book_value_chart', 'capital_chart'}
    assert chart_data['book_value_chart']['categories'] == ['النمو Growth']
    assert chart_data['capital_chart']['categories'] == ['النمو Growth']
    assert chart_data['book_value_chart']['values'] == [8675.0]
    assert chart_data['capital_chart']['values'] == [8500.0]
    assert chart_data['book_value_chart']['total'] == 8675.0
    assert chart_data['capital_chart']['total'] == 8500.0

    for removed_card_label in (
        'TOTAL CAPITAL',
        'TOTAL CASH',
        'POSITIONS',
        'TOTAL INCOME',
    ):
        assert removed_card_label not in row_text

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
    assert '8,675.00' in row_text
    assert '+75.00' in row_text
    assert '+100.00' in row_text
    assert '+1.75%' in row_text
    assert f'href="/transactions/?portfolio={quote_plus(portfolio.name)}"' in html


def test_overview_empty_portfolios_render_empty_chart_context(app):
    with app.app_context():
        uid = _seed_user('overview_empty')

    client = app.test_client()
    _login(client, uid)
    response = client.get('/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    text = _visible_text(html)
    chart_data = _chart_data(html)

    assert 'No portfolios yet' in text
    assert 'No book value data available.' in text
    assert 'No total capital data available.' in text
    assert html.count('<canvas') == 2
    assert chart_data['book_value_chart']['categories'] == []
    assert chart_data['book_value_chart']['allocations'] == []
    assert chart_data['book_value_chart']['values'] == []
    assert chart_data['book_value_chart']['total'] == 0.0
    assert chart_data['capital_chart']['categories'] == []
    assert chart_data['capital_chart']['allocations'] == []
    assert chart_data['capital_chart']['values'] == []
    assert chart_data['capital_chart']['total'] == 0.0
    assert 'sample' not in text.lower()
    assert 'demo' not in text.lower()


def test_overview_keeps_related_routes_available(app):
    with app.app_context():
        uid = _seed_user('overview_routes')

    client = app.test_client()
    _login(client, uid)

    assert client.get('/charts').status_code == 200
    assert client.get('/portfolios/').status_code == 200
    assert client.get('/transactions/').status_code == 200
