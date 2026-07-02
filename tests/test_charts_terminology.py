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
        'Portfolio Allocation',
        'By Book Value',
        'Portfolio Performance',
        'Portfolio Performance Over Time',
        'Asset Performance',
        'Asset Performance Over Time',
        'Realized P&L',
        'Return',
        'Income',
        'Best Month',
        'Worst Month',
        'Best Asset',
        'Worst Asset',
        'Assets performance, income, and return',
    ):
        assert label in text

    assert '<canvas id="allocationChart"></canvas>' in html
    assert '<canvas id="portfolioPerformanceChart"></canvas>' in html
    assert '<canvas id="assetPerformanceChart"></canvas>' in html
    assert "label: 'BOOK VALUE'" in html
    assert 'Other Portfolios' not in data['donut_categories']

    assert 'id="portfolioTrendChart"' not in html
    assert 'data-asset-summary-table' in html
    assert 'comparison-track' not in html
    assert 'data-comparison-table=' not in html
    assert 'data-leaderboard=' not in html
    assert 'bar_width' not in html
    assert 'renderAreaChart' in html
    assert "fill: true" in html
    assert "yAxisID: 'yPnl'" in html
    assert "yAxisID: 'yReturn'" in html
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

    assert all('realized_pnl' in item and 'return_percent' in item for item in data['portfolio_performance'])
    assert all('realized_pnl' in item and 'return_percent' in item for item in data['asset_performance'])
    assert set(('realized_pnl', 'return_percent', 'income', 'best_month', 'worst_month')).issubset(data['portfolio_stats'])
    assert set(('realized_pnl', 'return_percent', 'income', 'best_asset', 'worst_asset')).issubset(data['asset_stats'])
    assert set(('months', 'realized_pnl', 'return_percent', 'income', 'stats')).issubset(data['portfolio_trend'])
    assert set(('months', 'realized_pnl', 'return_percent', 'income', 'stats')).issubset(data['asset_trend'])

    assert any(item['name'] == 'النمو Growth' for item in data['portfolio_performance'])
    assert any(item['name'] == 'AAPL' for item in data['asset_performance'])

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

    assert 'Other Portfolios' not in seven_data['donut_categories']
    assert 'Other Portfolios' in eight_data['donut_categories']
    assert eight_data['donut_categories'][-1] == 'Other Portfolios'
    assert len(eight_data['donut_categories']) == 8
    assert sum(1 for name in eight_data['donut_categories'] if name.startswith('Allocated ')) == 7


def test_asset_summary_groups_long_lists_with_other_assets_row(app):
    with app.app_context():
        uid = _seed_user('many_performance')
        for idx in range(10):
            _seed_portfolio_with_asset(
                uid,
                portfolio_name=f'Perf {idx + 1}',
                symbol=f'P{idx + 1}',
                sell_price=str(80 + idx * 5),
            )

        svc = Services(user_id=uid)
        asset_portfolio = svc.portfolio_service.create_portfolio('Asset Bucket', user_id=uid)
        svc.portfolio_service.deposit_funds(
            asset_portfolio.id, _dec('20000'), date=datetime(2024, 1, 1),
        )
        for idx in range(21):
            _seed_asset(
                uid,
                asset_portfolio.id,
                symbol=f'AS{idx + 1}',
                sell_price=str(70 + idx * 5),
            )

    html = _get_charts_html(app, uid)
    data = _chart_data(html)
    asset_block = _asset_table_block(html)

    assert len(data['portfolio_performance']) == 11
    assert len(data['asset_performance']) > 20
    assert len(data['asset_performance_display']) == 8
    assert data['asset_performance_limited'] is True
    assert data['asset_performance_display'][-1]['name'] == 'Other Assets'
    assert data['asset_performance_display'][-1]['portfolio_names'] == ['Multiple']
    assert data['asset_performance_display'][-1]['is_other'] is True
    assert data['asset_performance_display'][-1]['return_percent'] is not None
    assert 'Showing top 7 assets and grouping the rest as Other Assets.' in asset_block

    assert 'Other Assets' in html
    assert 'Other</' not in html
    assert 'Other Portfolios' in html


def test_area_dashboard_renders_negative_values_and_ranges(app):
    with app.app_context():
        uid = _seed_user('negative_comparison')
        _seed_portfolio_with_asset(
            uid,
            portfolio_name='Loss Portfolio',
            symbol='LOSS',
            sell_price='75',
        )

    html = _get_charts_html(app, uid)
    data = _chart_data(html)
    asset_row = next(item for item in data['asset_performance_display'] if item['name'] == 'LOSS')

    assert data['portfolio_stats']['realized_pnl'] < 0
    assert data['portfolio_stats']['return_percent'] < 0
    assert data['asset_stats']['realized_pnl'] < 0
    assert data['asset_stats']['return_percent'] < 0
    assert any(value < 0 for value in data['portfolio_trend']['realized_pnl'])
    assert any(value < 0 for value in data['portfolio_trend']['return_percent'])
    assert any(value < 0 for value in data['asset_trend']['realized_pnl'])
    assert any(value < 0 for value in data['asset_trend']['return_percent'])
    assert asset_row['realized_pnl'] < 0
    assert asset_row['return_percent'] < 0
    assert data['asset_stats']['worst_asset']['label'] == 'LOSS'
    assert 'class="mini-stat-value loss"' in html
    assert 'class="asset-number loss"' in html
    assert 'min: pnlBounds.min' in html
    assert 'max: returnBounds.max' in html
