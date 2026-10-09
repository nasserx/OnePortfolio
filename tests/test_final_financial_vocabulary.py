"""Phase 9: one domain vocabulary, equivalent finances and accessible formula help."""

from datetime import datetime
from decimal import Decimal as D
from html.parser import HTMLParser
from html import escape

import pytest

from portfolio_app.calculators import PortfolioCalculator as PC
from portfolio_app.models import Dividend
from tests._auth import authenticate_client
from tests._financial import expected_percent
from tests.test_financial_baseline import ledger, _historical_trade


class FinancialPage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.button_depth = 0
        self.skip = 0
        self.labels = []
        self.help = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button':
            self.button_depth += 1
        if tag in ('script', 'style'):
            self.skip += 1
        if 'info-dot' in attrs.get('class', '').split():
            self.help.append((attrs, self.button_depth))

    def handle_endtag(self, tag):
        if tag == 'button':
            self.button_depth -= 1
        if tag in ('script', 'style'):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.labels.append(data.strip())


def _seed(ledger):
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('1000'))
    _historical_trade(ledger, 'Buy', '100', '2', 1)
    sale = _historical_trade(ledger, 'Sell', '120', '1', 2)
    ledger.svc.transaction_service.add_dividend(ledger.pid, 'BTC', D('5'), datetime(2024, 1, 3))
    return sale


def _page(app, ledger, url):
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    response = client.get(url)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    return html, FinancialPage(html)


@pytest.mark.parametrize('url,labels', [
    ('/', ['Book Value', 'Realized Return', 'Net Contributions', 'Cash', 'Dividends', 'Realized P&L']),
    ('/portfolios/', ['Entries', 'Net Contributions', 'Cash', 'Cost Basis']),
    ('/transactions/', ['Entries', 'Purchase Cost', 'Quantity', 'Avg. Cost',
                       'Realized P&L', 'Realized Return', 'Dividends']),
])
def test_concise_page_vocabulary_is_separate_from_precise_domain_names(ledger, app, url, labels):
    _seed(ledger)
    html, page = _page(app, ledger, url)
    assert set(labels) <= set(page.labels)
    assert not {'Capital', 'Total Capital', 'Total Cash', 'Positions', 'Total Spent',
                'Average Cost', 'Income', 'Total Income', 'Cash Balance',
                'Dividend Income', 'Realized Trading P&L', 'Realized Trading Return',
                'Total Purchase Cost', 'Average Unit Cost', 'Position Cost Basis',
                'Total Realized Earnings'} & set(page.labels)
    if url == '/transactions/':
        assert '<th class="records-cell records-cell--number">Return</th>' in html
    else:
        assert 'Return' not in page.labels
    if url == '/portfolios/':
        assert 'Book Value' not in page.labels
        assert '1,000.00' in page.labels
        assert '925.00' in page.labels
        assert '100.00' in page.labels
    if url == '/':
        assert '+20.00%' in page.labels
        assert '+25.00' not in page.labels  # earnings remain internal, no redundant card


def test_overview_has_only_three_focusable_formula_indicators(ledger, app):
    _seed(ledger)
    _, page = _page(app, ledger, '/')
    assert len(page.help) == 3
    expected = {
        'Book Value = Cash + Cost Basis',
        'Net Contributions = Deposits − Withdrawals',
        'Realized P&L = Net Sale Proceeds − Released Cost Basis\n'
        'Realized Return = Realized P&L ÷ Released Cost Basis × 100',
    }
    assert {attrs['aria-label'] for attrs, _ in page.help} == expected
    for attrs, button_depth in page.help:
        assert button_depth == 1
        assert attrs['type'] == 'button'
        assert 'tabindex' not in attrs
        assert 'role' not in attrs
        assert attrs['aria-label'] == attrs['title']
        assert attrs['data-bs-toggle'] == 'tooltip'
        assert attrs['data-bs-trigger'] == 'hover focus'
        assert attrs['data-bs-html'] == 'true'
        expected_lines = []
        for line in attrs['aria-label'].split('\n'):
            name, formula = line.split('=', 1)
            expected_lines.append(
                '<span class="tooltip-formula">'
                f'<strong>{escape(name.strip())}</strong> = {escape(formula.strip())}'
                '</span>'
            )
        assert attrs['data-bs-title'] == (
            '<span class="tooltip-formulas">' + ''.join(expected_lines) + '</span>'
        )


@pytest.mark.parametrize('url', ['/portfolios/', '/transactions/'])
def test_dense_summaries_do_not_have_help_indicators(ledger, app, url):
    _seed(ledger)
    _, page = _page(app, ledger, url)
    assert not page.help



def test_negative_contributions_are_not_presented_as_a_loss(ledger, app):
    _historical_trade(ledger, 'Buy', '185000', '.003', 1)
    ledger.svc.portfolio_service.deposit_funds(ledger.pid, D('555'))
    _historical_trade(ledger, 'Sell', '186000', '.003', 2)
    ledger.svc.portfolio_service.withdraw_funds(ledger.pid, D('558'))
    _, page = _page(app, ledger, '/portfolios/')
    assert '-3.00' in page.labels
    assert 'Net Contributions' in page.labels
    assert not any('loss' in label.lower() for label in page.labels)
    snapshot = PC.get_portfolio_snapshot(ledger.pid, user_id=ledger.uid)
    assert snapshot.metrics['realized_trading_pnl'] == D('3')
    assert snapshot.metrics['realized_trading_return'] == expected_percent('3', '555')


def test_canonical_api_keys_are_exact_and_old_aliases_are_absent(ledger, app):
    sale = _seed(ledger)
    client = app.test_client()
    authenticate_client(client, ledger.uid)
    payload = client.get('/api/portfolio-summary').get_json()
    assert payload['book_value'] == '1025'
    assert 'total_value' not in payload
    row = payload['portfolio_summary'][0]
    expected = {'gross_deposits': '1000', 'net_contributions': '1000', 'cash_balance': '925',
                'position_cost_basis': '100', 'book_value': '1025', 'dividend_income': '5',
                'realized_trading_pnl': '20', 'released_cost_basis': '100',
                'total_realized_earnings': '25', 'realized_trading_return': '20.0'}
    for key, value in expected.items():
        assert row[key] == value
        assert isinstance(row[key], str)
    obsolete = {'total_contributed', 'total_capital', 'cash', 'positions', 'cost_basis',
                'realized_pnl', 'total_income', 'return_percent', 'return_display', 'return_amount'}
    assert not obsolete & row.keys()
    snapshot = PC.get_asset_snapshot(ledger.pid, 'BTC', user_id=ledger.uid)
    assert not hasattr(snapshot, 'income')
    assert not hasattr(snapshot, 'returns')
    transaction = sale.to_dict(projection=snapshot.transaction_projections[sale.id], portfolio_name='BTC')
    assert transaction['transaction_amount'] == '120'
    assert transaction['applicable_average_unit_cost'] == '100'
    assert transaction['realized_trading_pnl'] == '20'
    assert transaction['realized_trading_return'] == '20.0'
    assert not {'net_amount', 'average_cost', 'net_pnl', 'net_pnl_percent'} & transaction.keys()
    assert Dividend.__tablename__ == 'dividend'


@pytest.mark.parametrize('sale_price,shown', [(None, '—'), ('100', '0.00%')])
def test_undefined_and_genuine_zero_remain_distinct_with_final_labels(ledger, app, sale_price, shown):
    _historical_trade(ledger, 'Buy', '100', '1', 1)
    if sale_price:
        _historical_trade(ledger, 'Sell', sale_price, '1', 2)
    _, page = _page(app, ledger, '/')
    assert 'Realized Return' in page.labels
    assert shown in page.labels
