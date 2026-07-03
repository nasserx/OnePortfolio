import re
from html.parser import HTMLParser
from pathlib import Path

from portfolio_app import db
from portfolio_app.models.user import User


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


def _visible_text(html):
    parser = _VisibleTextParser()
    parser.feed(html)
    return '\n'.join(parser.parts)


def _landing_html(app):
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _landing_script():
    return Path('portfolio_app/static/js/landing.js').read_text(encoding='utf-8')


def _quoted(value):
    return rf"['\"]{re.escape(value)}['\"]"


def _portfolio_block(script, key):
    match = re.search(
        rf"key:\s*{_quoted(key)}\s*,(?P<body>.*?)(?=\n\s*}}\s*,|\n\s*}}\s*\])",
        script,
        re.DOTALL,
    )
    assert match is not None
    return match.group('body')


def test_landing_rebuild_renders_public_sample_preview(app):
    html = _landing_html(app)
    text = _visible_text(html)

    assert html.count('<h1') == 1
    assert '<h1 id="landing-heading">Track your portfolios manually, with clarity and control.</h1>' in html
    assert 'Sample portfolio' in text
    assert 'By Book Value' in text
    assert 'By Capital' in text
    assert html.count('class="landing-chart-canvas"') == 2
    assert 'id="landingBookValueChart"' in html
    assert 'id="landingCapitalChart"' in html

    row_text = html[html.index('aria-label="Sample portfolio records"'):]

    for label in ('Portfolio', 'Book Value', 'Income', 'Realized P&L', 'Return'):
        assert label in text

    for portfolio in ('Stocks', 'ETFs', 'Crypto'):
        assert portfolio in text

    assert 'class="landing-sample-table"' in html
    assert len(re.findall(r'<article class="landing-table-row" role="row">', row_text)) == 3
    assert 'class="overview-portfolio-marker allocation-marker-1"' in html
    assert 'class="overview-portfolio-marker allocation-marker-3"' in html
    assert 'class="overview-portfolio-marker allocation-marker-4"' not in html
    assert 'href="/transactions/?portfolio=' not in row_text
    assert 'data-landing-metric="bookValue"' in html
    assert 'data-landing-metric="totalCapital"' in html
    assert 'data-landing-metric="totalCash"' in html
    assert 'data-landing-metric="totalIncome"' in html
    assert 'data-landing-metric="realizedPnl"' in html
    for row in ('stocks', 'etfs', 'crypto'):
        assert f'data-landing-row="{row}" data-landing-field="return"' in html

    assert 'MANUAL PORTFOLIO TRACKING' not in text
    assert 'Marketing preview' not in text
    assert 'Supported record fields' not in text
    assert 'Gold' not in text
    assert 'Bonds' not in text
    assert 'AAPL' not in text
    assert 'VOO' not in text
    assert 'BTC' not in text
    assert 'GLD' not in text
    assert 'BND' not in text
    assert '124,650.00' not in text
    assert '137,890.30' not in text
    assert '15,300.00' not in text
    assert '11,200.00' not in text
    assert '12,100.00' not in text
    assert '1,600.00' not in text
    assert '360.00' not in text
    assert '+760.00' not in text


def test_landing_data_source_contains_expected_sample_portfolios():
    script = _landing_script()

    assert len(re.findall(r"key:\s*['\"](?:stocks|etfs|crypto)['\"]", script)) == 3
    for key, name in (('stocks', 'Stocks'), ('etfs', 'ETFs'), ('crypto', 'Crypto')):
        assert re.search(rf"key:\s*{_quoted(key)}", script)
        assert re.search(rf"name:\s*{_quoted(name)}", script)

    assert re.search(r"canvasId:\s*['\"]landingBookValueChart['\"]", script)
    assert re.search(r"legendId:\s*['\"]landingBookValueLegend['\"]", script)
    assert re.search(r"valueKey:\s*['\"]bookValue['\"]", script)
    assert re.search(r"canvasId:\s*['\"]landingCapitalChart['\"]", script)
    assert re.search(r"legendId:\s*['\"]landingCapitalLegend['\"]", script)
    assert re.search(r"valueKey:\s*['\"]capital['\"]", script)

    assert 'Gold' not in script
    assert 'Bonds' not in script
    assert '5200' not in script
    assert '11200' not in script
    assert '12100' not in script
    assert 'landingBookValueChart' in script
    assert 'landingCapitalChart' in script


def test_landing_sample_values_match_approved_data():
    script = _landing_script()

    expected = {
        'stocks': {
            'name': 'Stocks',
            'bookValue': '18000',
            'capital': '20000',
            'income': '1100',
            'realizedPnl': '1700',
            'return': '+16%',
        },
        'etfs': {
            'name': 'ETFs',
            'bookValue': '14000',
            'capital': '16000',
            'income': '800',
            'realizedPnl': '1200',
            'return': '+14%',
        },
        'crypto': {
            'name': 'Crypto',
            'bookValue': '10000',
            'capital': '12000',
            'income': '500',
            'realizedPnl': '700',
            'return': '+12%',
        },
    }

    for key, fields in expected.items():
        block = _portfolio_block(script, key)
        assert re.search(rf"name:\s*{_quoted(fields['name'])}", block)
        for field in ('bookValue', 'capital', 'income', 'realizedPnl'):
            assert re.search(rf"{field}:\s*{fields[field]}\s*,", block)
        assert re.search(rf"return:\s*{_quoted(fields['return'])}", block)

    assert re.search(r"cash:\s*6000\s*,", script)
    assert re.search(r"income:\s*2400\s*,", script)
    assert re.search(r"realizedPnl:\s*3600\s*,", script)
    assert len(re.findall(r"return:\s*['\"]\+\d+%['\"]", script)) == 3
    assert "maximumFractionDigits: 0" in script
    assert "formatSignedNumber(sampleData.totals.realizedPnl)" in script

    expected_rendered = {
        'Book Value': f"{sum(int(row['bookValue']) for row in expected.values()):,}",
        'Total Capital': f"{sum(int(row['capital']) for row in expected.values()):,}",
        'Total Cash': f"{6000:,}",
        'Total Income': f"{2400:,}",
        'Realized P&L': f"+{3600:,}",
        'Stocks Book Value': f"{int(expected['stocks']['bookValue']):,}",
        'Stocks Income': f"+{int(expected['stocks']['income']):,}",
        'Stocks Realized P&L': f"+{int(expected['stocks']['realizedPnl']):,}",
        'Stocks Return': expected['stocks']['return'],
        'ETFs Book Value': f"{int(expected['etfs']['bookValue']):,}",
        'ETFs Income': f"+{int(expected['etfs']['income']):,}",
        'ETFs Realized P&L': f"+{int(expected['etfs']['realizedPnl']):,}",
        'ETFs Return': expected['etfs']['return'],
        'Crypto Book Value': f"{int(expected['crypto']['bookValue']):,}",
        'Crypto Income': f"+{int(expected['crypto']['income']):,}",
        'Crypto Realized P&L': f"+{int(expected['crypto']['realizedPnl']):,}",
        'Crypto Return': expected['crypto']['return'],
    }
    assert expected_rendered == {
        'Book Value': '42,000',
        'Total Capital': '48,000',
        'Total Cash': '6,000',
        'Total Income': '2,400',
        'Realized P&L': '+3,600',
        'Stocks Book Value': '18,000',
        'Stocks Income': '+1,100',
        'Stocks Realized P&L': '+1,700',
        'Stocks Return': '+16%',
        'ETFs Book Value': '14,000',
        'ETFs Income': '+800',
        'ETFs Realized P&L': '+1,200',
        'ETFs Return': '+14%',
        'Crypto Book Value': '10,000',
        'Crypto Income': '+500',
        'Crypto Realized P&L': '+700',
        'Crypto Return': '+12%',
    }


def test_landing_links_anchors_and_removed_terms(app):
    html = _landing_html(app)
    text = _visible_text(html)
    lower_text = text.lower()

    assert 'class="btn-nav-login" href="/login"' in html
    assert 'class="btn-nav-signup" href="/register"' in html
    assert 'class="landing-nav-links"' not in html
    assert 'class="btn-cta-primary" href="/register"' in html
    assert 'class="btn-cta-secondary" href="/login"' in html
    assert 'href="#features"' in html
    assert 'id="features"' in html
    assert 'href="#how-it-works"' in html
    assert 'id="how-it-works"' in html

    assert 'Market Value' not in html
    assert 'Unrealized P&L' not in html
    assert 'Manual by design' in text
    assert 'No market feeds' in text
    assert 'without live prices' in lower_text
    assert 'no live prices' in lower_text
    assert 'broker connections' in lower_text
    assert 'broker sync' in lower_text
    assert 'live pricing' not in lower_text
    assert 'broker integration' not in lower_text
    assert 'sync your broker' not in lower_text
    assert 'market value' not in lower_text
    assert 'unrealized p&l' not in lower_text
    assert 'Track your portfolios with clarity.' not in text
    assert 'Track your portfolios with clarity and control.' not in text
    assert 'Built for practical tracking' not in text
    assert 'class="landing-card"' not in html
    assert 'class="support-card"' not in html


def test_authenticated_root_still_renders_internal_overview(app):
    with app.app_context():
        user = User(username='landing_user', email='landing@example.com', is_verified=True)
        user.set_password('test-password')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Track your portfolios manually, with clarity and control.' not in html
    assert 'Overview' in _visible_text(html)
