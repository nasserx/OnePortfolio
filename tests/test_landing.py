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


class _ClassTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == 'class' and value:
                self.tokens.update(value.split())


def _visible_text(html):
    parser = _VisibleTextParser()
    parser.feed(html)
    return '\n'.join(parser.parts)


def _class_tokens(html):
    parser = _ClassTokenParser()
    parser.feed(html)
    return parser.tokens


def _landing_html(app):
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _landing_script():
    return Path('portfolio_app/static/js/landing.js').read_text(encoding='utf-8')


def _sample_number(script, path):
    """Pull a numeric literal out of the SAMPLE object in landing.js."""
    match = re.search(rf"{re.escape(path)}:\s*(-?\d+(?:\.\d+)?)", script)
    assert match is not None, f'{path} not found in landing.js'
    return float(match.group(1))


def test_landing_renders_public_product_preview(app):
    html = _landing_html(app)
    text = _visible_text(html)

    assert html.count('<h1') == 1
    assert 'A clear record of every portfolio you manage.' in text

    # The preview is one allocation ring driven entirely by data hooks; no
    # figure may be typed into the markup.
    assert html.count('<canvas') == 1
    assert 'id="landingChart"' in html
    assert 'id="landingLegend"' in html

    for hook in ('bookValue', 'totalCapital', 'totalCash',
                 'totalIncome', 'realizedPnl', 'returnPercent'):
        assert f'data-landing-metric="{hook}"' in html

    for label in ('Book value', 'Total capital', 'Total cash',
                  'Income', 'Realized P&L'):
        assert label in text

    # Preview figures are rendered by landing.js, so none may be baked in.
    assert not re.search(r'>\s*\d{1,3},\d{3}\.\d{2}\s*<', html)

    # Sample portfolio names come from the script, not the template.
    script = _landing_script()
    for portfolio in ('Stocks', 'ETFs', 'Crypto'):
        assert f"'{portfolio}'" in script
        assert portfolio not in text

    for stale in ('Gold', 'Bonds', 'AAPL', 'VOO', 'BTC', 'GLD', 'BND',
                  'Marketing preview', 'Supported record fields'):
        assert stale not in text


def test_landing_hero_is_not_bound_to_the_root_scroll_timeline(app):
    html = _landing_html(app)
    classes = _class_tokens(html)
    landing_styles = '\n'.join(
        Path('portfolio_app/static/css', name).read_text(encoding='utf-8')
        for name in ('tokens.css', 'base.css', 'components.css', 'landing.css')
    ).lower()

    # Keep the photograph and its static shade, but never bind that full-size
    # layer to root scrolling. That contract triggered multi-second boundary-
    # overscroll stalls in desktop Chromium.
    assert 'hero-media' in classes
    assert '/static/img/hero.avif' in html
    assert '/static/img/hero.webp' in html
    assert 'hero-media--lift' not in classes

    for removed_contract in (
        'hero-media--lift',
        'op-hero-lift',
        '--hero-lift-range',
    ):
        assert removed_contract not in landing_styles

    for forbidden_property in ('animation-timeline', 'scroll-timeline'):
        assert forbidden_property not in landing_styles


def test_landing_sample_data_is_internally_consistent():
    """The preview's totals must be derived from the sample rows rather than
    hand-typed, so the marketing screenshot can never contradict itself."""
    script = _landing_script()

    book_values = [float(v) for v in re.findall(r'bookValue:\s*(\d+)', script)]
    capitals = [float(v) for v in re.findall(r'capital:\s*(\d+)', script)]

    assert len(book_values) == 3
    assert len(capitals) == 3

    # Totals are computed in JS, never written as literals.
    assert 'function total(' in script
    assert "total('bookValue')" in script
    assert "total('capital')" in script

    # The headline return is derived from realized P&L over total capital.
    assert 'SAMPLE.realizedPnl / capital' in script
    assert 'returnPercent' in script

    cash = _sample_number(script, 'cash')
    income = _sample_number(script, 'income')
    realized = _sample_number(script, 'realizedPnl')

    # Sanity: a plausible, positive sample book that is smaller than capital
    # (book value net of withdrawals) with non-negative income.
    assert 0 < sum(book_values) < sum(capitals)
    assert cash > 0
    assert income >= 0
    assert realized >= 0

    for stale in ('Gold', 'Bonds', 'landingBookValueChart', 'landingCapitalChart'):
        assert stale not in script


def test_landing_links_anchors_and_removed_terms(app):
    html = _landing_html(app)
    text = _visible_text(html)
    lower_text = text.lower()

    assert 'href="/login"' in html
    assert 'href="/register"' in html

    # Every in-page anchor must resolve to a section that actually exists.
    anchors = set(re.findall(r'href="#([\w-]+)"', html))
    assert anchors
    for anchor in anchors:
        assert f'id="{anchor}"' in html

    assert 'Manual by design' in text
    assert 'No market feeds' in text
    assert 'no live prices' in lower_text
    assert 'broker connections' in lower_text
    assert 'broker sync' in lower_text

    # Positioning guardrails: this product does not price positions.
    assert 'live pricing' not in lower_text
    assert 'broker integration' not in lower_text
    assert 'sync your broker' not in lower_text
    assert 'market value' not in lower_text
    assert 'unrealized p&l' not in lower_text
    assert 'Track your portfolios with clarity.' not in text
    assert 'Built for practical tracking' not in text


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
    assert 'A clear record of every portfolio you manage.' not in html
    assert 'Overview' in _visible_text(html)
