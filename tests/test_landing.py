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


def test_landing_rebuild_renders_public_sample_preview(app):
    html = _landing_html(app)
    text = _visible_text(html)

    assert '<h1 id="landing-heading">Track your portfolios with clarity and control.</h1>' in html
    assert 'Sample portfolio' in text
    assert 'By Book Value' in text
    assert 'By Capital' in text
    assert html.count('class="landing-chart-canvas"') == 2
    assert 'id="landingBookValueChart"' in html
    assert 'id="landingCapitalChart"' in html

    row_text = html[html.index('aria-label="Sample portfolios"'):]

    for label in ('Portfolio', 'Book Value', 'Income', 'Realized P&L', 'Return', 'Assets'):
        assert label in text

    for portfolio in ('Stocks', 'ETFs', 'Crypto'):
        assert portfolio in text

    assert 'class="overview-portfolio-table landing-sample-table"' in html
    assert len(re.findall(r'<article class="overview-portfolio-row" role="row">', row_text)) == 3
    assert 'class="overview-portfolio-marker allocation-marker-1"' in html
    assert 'class="overview-portfolio-marker allocation-marker-3"' in html
    assert 'class="overview-portfolio-marker allocation-marker-4"' not in html
    assert text.count('View Assets →') == 3
    assert 'href="/transactions/?portfolio=' not in row_text
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
    assert '14,000.00' not in text
    assert '15,300.00' not in text
    assert '11,200.00' in text
    assert '12,100.00' in text
    assert '1,600.00' in text
    assert '360.00' in text
    assert '+760.00' in text


def test_landing_data_source_contains_expected_sample_portfolios():
    script = Path('portfolio_app/static/js/landing.js').read_text(encoding='utf-8')
    match = re.search(r"portfolios:\s*\[(.*?)\]", script, re.DOTALL)
    assert match is not None

    labels = re.findall(r"'([^']+)'", match.group(1))
    assert labels == ['Stocks', 'ETFs', 'Crypto']
    assert 'Gold' not in script
    assert 'Bonds' not in script
    assert 'values: [5200, 3600, 2400]' in script
    assert 'total: 11200' in script
    assert 'values: [5600, 3900, 2600]' in script
    assert 'total: 12100' in script
    assert script.count('renderDoughnut(') == 3
    assert 'landingBookValueChart' in script
    assert 'landingCapitalChart' in script


def test_landing_links_anchors_and_removed_terms(app):
    html = _landing_html(app)
    text = _visible_text(html)

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
    assert 'live prices' not in html
    assert 'Track your portfolios with clarity.' not in text
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
    assert 'Track your portfolios with clarity and control.' not in html
    assert 'Overview' in _visible_text(html)
