from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
import json
import re

from portfolio_app import db
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


def _seed_user(username='charts_user'):
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


def _asset_table_block(html):
    marker = 'data-asset-summary-table'
    start = html.index(marker)
    return html[start:]


def _chart_data(html):
    match = re.search(r'const chartData = (\{.*?\});', html, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


def _seed_portfolio_with_asset(uid, *, portfolio_name, symbol, sell_price, year=None):
    year = year or datetime.now().year
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio(portfolio_name, user_id=uid)
    svc.portfolio_service.deposit_funds(
        portfolio.id, _dec('5000'), date=datetime(year, 1, 1),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Buy',
        symbol=symbol,
        price=_dec('100'),
        quantity=_dec('1'),
        fees=_dec('0'),
        date=datetime(year, 1, 2),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id,
        transaction_type='Sell',
        symbol=symbol,
        price=_dec(str(sell_price)),
        quantity=_dec('1'),
        fees=_dec('0'),
        date=datetime(year, 1, 3),
    )
    return portfolio


def _seed_asset(uid, portfolio_id, *, symbol, sell_price, year=None):
    year = year or datetime.now().year
    svc = Services(user_id=uid)
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio_id,
        transaction_type='Buy',
        symbol=symbol,
        price=_dec('100'),
        quantity=_dec('1'),
        fees=_dec('0'),
        date=datetime(year, 2, 1),
    )
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio_id,
        transaction_type='Sell',
        symbol=symbol,
        price=_dec(str(sell_price)),
        quantity=_dec('1'),
        fees=_dec('0'),
        date=datetime(year, 2, 2),
    )


def _get_charts_html(app, uid):
    client = app.test_client()
    _login(client, uid)
    response = client.get('/charts')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_charts_page_uses_dashboard_cards_and_current_terminology(app):
    with app.app_context():
        uid = _seed_user()
        _seed_portfolio_with_asset(
            uid, portfolio_name='النمو Growth', symbol='AAPL', sell_price='125',
        )

    html = _get_charts_html(app, uid)
    data = _chart_data(html)
    text = _visible_text(html)

    for label in (
        'By Book Value',
        'By Capital',
    ):
        assert label in text

    for removed_label in (
        'Portfolio Allocation',
        'Portfolio Performance',
        'Portfolio Performance Over Time',
        'Asset Performance',
        'Asset Performance Over Time',
        'Best Month',
        'Worst Month',
        'Best Asset',
        'Worst Asset',
        'Assets performance, income, and return',
    ):
        assert removed_label not in text

    assert '<canvas id="bookValueChart"' in html
    assert '<canvas id="bookCapitalChart"' in html
    assert '<canvas id="portfolioPerformanceChart"' not in html
    assert '<canvas id="assetPerformanceChart"' not in html
    assert "centerLabel: 'BOOK VALUE'" in html
    assert "centerLabel: 'CAPITAL'" in html
    assert 'Other Portfolios' not in data['book_value_chart']['categories']
    assert 'Other Portfolios' not in data['capital_chart']['categories']

    assert 'id="portfolioTrendChart"' not in html
    assert 'data-asset-summary-table' not in html
    assert 'comparison-track' not in html
    assert 'data-comparison-table=' not in html
    assert 'data-leaderboard=' not in html
    assert 'bar_width' not in html
    assert 'renderAreaChart' not in html
    assert "yAxisID: 'yPnl'" not in html
    assert "yAxisID: 'yReturn'" not in html
    assert 'data-heatmap' not in html
    assert 'Heatmap' not in html
    assert 'Treemap' not in html
    assert 'treemap' not in html
    assert 'chartjs-chart-treemap' not in html

    assert '<select' not in html
    assert 'data-trend-metric' not in html
    assert 'data-leaderboard-metric' not in html
    assert 'trendMetricSelect' not in html
    assert 'portfolioLeaderboardMetric' not in html
    assert 'assetLeaderboardMetric' not in html
    assert 'This Year' not in text
    assert 'Showing all portfolios.' not in text
    assert 'Showing all assets.' not in text

    assert set(data) == {'book_value_chart', 'capital_chart'}
    assert data['book_value_chart']['categories'] == ['النمو Growth']
    assert data['capital_chart']['categories'] == ['النمو Growth']
    assert data['book_value_chart']['values'] == [5025.0]
    assert data['capital_chart']['values'] == [5000.0]
    assert data['book_value_chart']['total'] == 5025.0
    assert data['capital_chart']['total'] == 5000.0

    for old_label in (
        'Symbol Performance',
        'Market Value',
        'Unrealized P&L',
    ):
        assert old_label not in text

    assert 'ROI' not in text
    assert 'TOTAL' not in text
    assert 'USD' not in text
    assert not re.search(r'(?<!Realized )\bP&L\b', text)


def test_portfolio_allocation_uses_other_portfolios_only_after_seven(app):
    with app.app_context():
        uid_seven = _seed_user('seven_portfolios')
        for idx in range(7):
            _seed_portfolio_with_asset(
                uid_seven,
                portfolio_name=f'Portfolio {idx + 1}',
                symbol=f'S{idx + 1}',
                sell_price=str(105 + idx),
            )

        uid_eight = _seed_user('eight_portfolios')
        for idx in range(8):
            _seed_portfolio_with_asset(
                uid_eight,
                portfolio_name=f'Allocated {idx + 1}',
                symbol=f'A{idx + 1}',
                sell_price=str(105 + idx),
            )

    seven_html = _get_charts_html(app, uid_seven)
    eight_html = _get_charts_html(app, uid_eight)
    seven_data = _chart_data(seven_html)
    eight_data = _chart_data(eight_html)

    assert 'Other Portfolios' not in seven_data['book_value_chart']['categories']
    assert 'Other Portfolios' not in seven_data['capital_chart']['categories']
    assert 'Other Portfolios' in eight_data['book_value_chart']['categories']
    assert 'Other Portfolios' in eight_data['capital_chart']['categories']
    assert eight_data['book_value_chart']['categories'][-1] == 'Other Portfolios'
    assert eight_data['capital_chart']['categories'][-1] == 'Other Portfolios'
    assert len(eight_data['book_value_chart']['categories']) == 8
    assert len(eight_data['capital_chart']['categories']) == 8
    assert sum(1 for name in eight_data['book_value_chart']['categories'] if name.startswith('Allocated ')) == 7


def test_charts_page_handles_empty_chart_data(app):
    with app.app_context():
        uid = _seed_user('empty_charts')

    html = _get_charts_html(app, uid)
    data = _chart_data(html)
    text = _visible_text(html)

    assert 'By Book Value' in text
    assert 'By Capital' in text
    assert 'No book value data available.' in text
    assert 'No total capital data available.' in text
    assert data['book_value_chart']['categories'] == []
    assert data['book_value_chart']['allocations'] == []
    assert data['book_value_chart']['values'] == []
    assert data['book_value_chart']['total'] == 0.0
    assert data['capital_chart']['categories'] == []
    assert data['capital_chart']['allocations'] == []
    assert data['capital_chart']['values'] == []
    assert data['capital_chart']['total'] == 0.0
