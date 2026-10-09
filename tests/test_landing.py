import re
import json
from decimal import Decimal as D
from html.parser import HTMLParser
from pathlib import Path

from portfolio_app import db
from portfolio_app.models.user import User
from portfolio_app.services.overview_service import OverviewService
from tests._financial import expected_percent
from tests._auth import authenticate_client

_TOKENS = Path('portfolio_app/static/css/tokens.css')


# `svg` joins script and style because the only inline vector left on this
# page is the wordmark, which is a mark rather than copy. Counting glyphs
# inside it as visible text would point the stale-terminology checks below at
# something no reader is ever read.
_UNSPOKEN = {'script', 'style', 'svg'}


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in _UNSPOKEN:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in _UNSPOKEN and self._skip_depth:
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


def test_landing_renders_public_product_preview(app):
    html = _landing_html(app)
    text = _visible_text(html)

    assert html.count('<h1') == 1
    assert 'A clear record of every portfolio you manage.' in text

    # The preview keeps one allocation ring; metrics are server-rendered.
    assert html.count('<canvas') == 1
    assert 'id="landingChart"' in html
    assert 'id="landingLegend"' in html

    for hook in ('bookValue', 'netContributions', 'cashBalance',
                 'dividendIncome', 'totalRealizedEarnings', 'capitalReturn'):
        assert f'data-landing-metric="{hook}"' in html

    for label in ('Book Value', 'Net Contributions', 'Cash',
                  'Dividends', 'Cumulative P&L'):
        assert label in text

    assert '42,180.00' in text
    assert '+6,050.00' in text
    assert '+12.60%' in text

    # Exact public sample data supplies the chart; no private holdings are loaded.
    payload = json.loads(re.search(r'id="landing-preview-data" type="application/json">(.*?)</script>', html).group(1))
    for portfolio in ('Stocks', 'ETFs', 'Crypto'):
        assert portfolio in [p['name'] for p in payload]
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

    # There is no backdrop layer left to bind to anything, which is the
    # strongest form this contract has taken: the multi-second boundary-
    # overscroll stalls in desktop Chromium came from tying a full-bleed
    # decorative layer to root scrolling, and the layer itself is gone.
    for retired in ('hero-media', 'hero-media--lift', 'lp-heroart'):
        assert retired not in classes

    for removed_contract in (
        'hero-media--lift',
        'op-hero-lift',
        '--hero-lift-range',
    ):
        assert removed_contract not in landing_styles

    for forbidden_property in ('animation-timeline', 'scroll-timeline'):
        assert forbidden_property not in landing_styles


def _landing_css():
    return Path('portfolio_app/static/css/landing.css').read_text(encoding='utf-8')


def _rule(css, selector):
    """The declarations of one rule, by exact selector.

    `.lp-nav` must not match `.lp-nav__inner`, so the selector has to be
    followed by its brace and nothing else.
    """
    match = re.search(rf'{re.escape(selector)}\s*\{{([^}}]*)\}}', css)
    assert match is not None, f'no `{selector} {{ ... }}` rule in landing.css'
    return {
        name.strip(): value.strip()
        for name, value in re.findall(r'([\w-]+)\s*:\s*([^;]+);', match.group(1))
    }


def _canvas_mix(value):
    """Extract the canonical-background share from the translucent header."""
    match = re.fullmatch(
        r'color-mix\(\s*in oklch,\s*var\(\s*--background\s*\)\s*'
        r'([\d.]+)%\s*,\s*transparent\s*\)',
        value.strip(),
    )
    assert match is not None, (
        f'expected a --background/transparent color-mix, got {value!r}. The '
        f'header surface has to be made of the page colour: that is what '
        f'keeps it reading as page rather than as a bar.'
    )
    return float(match.group(1)) / 100


def test_landing_header_has_exactly_one_appearance():
    """One surface, no state, nothing watching the scroll position.

    The header used to have two appearances: invisible over the hero, then a
    panel once `landing.js` saw eight pixels of scroll. Both halves are gone
    on purpose. The invisible half needed a scroll listener to leave and left
    every control in the row reading against a photograph, so each carried a
    second set of colours that applied for the first eight pixels of the page
    and nowhere else — three rules, a class, a listener and an element id, to
    describe a state most visitors never saw.

    What this pins is the absence: no state class on `.lp-nav`, no rule that
    keys off one, and no scroll listener in the page's script. Reintroducing
    the two-state header means deleting this test, which is the point — it
    should be a decision, not a drift.
    """
    css = _landing_css()
    script = _landing_script()
    nav = _rule(css, '.lp-nav')

    # Translucent, so the picture still moves under it, and enough of the
    # page colour that the row is not read against bare photograph.
    fill = _canvas_mix(nav['background-color'])
    assert 0 < fill < 1, (
        f'the header is {fill:.0%} of the page colour; it is meant to be '
        f'translucent, not a lid and not absent'
    )
    assert 'blur(' in nav.get('backdrop-filter', ''), (
        'the header has no backdrop blur; the panel and the blur are the '
        'whole of what separates this row from the page moving under it'
    )

    # And they are the whole of it: no divider, at rest or after scrolling.
    # The panel already says where the header ends, so a hairline draws a
    # second edge in the same place — the hardest line on a page whose intro
    # is a soft gradient.
    assert not any(name.startswith('border') for name in nav), (
        f'`.lp-nav` declares {sorted(n for n in nav if n.startswith("border"))}; '
        f'the header has no divider in any state'
    )

    # No state class, and nothing keying off one. Both spellings: a rule that
    # adds a state (`.lp-nav.is-x`) and one that excludes it
    # (`.lp-nav:not(.is-x)`) are the same mechanism seen from either side.
    stateful = set(re.findall(r'\.lp-nav\.([\w-]+)', css))
    stateful |= set(re.findall(r'\.lp-nav:not\(\s*\.([\w-]+)\s*\)', css))
    assert not stateful, (
        f'`.lp-nav` is qualified by {sorted(stateful)}. The header has one '
        f'appearance; a qualifier here is a second one that nothing sets.'
    )

    # UI-STALL-01: the header was this page's only scroll listener.
    assert 'addEventListener(\'scroll\'' not in script, (
        'landing.js listens to scroll again. The header state it used to '
        'drive is gone, so this page should have no scroll listener at all.'
    )
    assert 'scrollY' not in script, (
        'landing.js reads the scroll position again. The header no longer '
        'needs it, and per-frame scroll work on this page is what '
        'UI-STALL-01 was about.'
    )


def test_landing_product_preview_composes_the_shared_card_surface():
    """The preview uses the application's card contract without repainting it."""
    css = _landing_css()
    card = _rule(css, '.lp-shot')
    template = Path('portfolio_app/templates/landing.html').read_text(encoding='utf-8')

    assert 'class="lp-shot surface-card"' in template
    assert 'lp-shot__chrome' not in template + css
    for visual_edge in ('border', 'border-radius', 'background-color', 'box-shadow'):
        assert visual_edge not in card


def test_landing_intro_carries_no_decorative_media(app):
    """The preview is the hero's only graphic; no decorative media is loaded."""
    html = _landing_html(app)

    for banned in ('/static/img/hero', 'hero-media', 'lp-heroart', '<picture'):
        assert banned not in html

    # The one canvas on this page is the product preview's allocation ring,
    # which is data rather than decoration.
    assert html.count('<canvas') == 1

    # Scoped to the intro rather than the page: the wordmark in the header is
    # an image and is meant to be. Inside this section, the only graphic is
    # the preview card's ring, which is the product drawing its own data —
    # the ban is on decoration, not on the product.
    start = html.index('<section class="lp-hero">')
    intro = html[start:html.index('</section>', start)]
    for element in ('<img', '<picture'):
        assert element not in intro, (
            f'{element}> inside the intro; apart from the preview card the '
            f'section carries type and nothing else'
        )
    assert '<path' not in intro
    assert '#op-icon-' in intro

    landing_css = _landing_css()
    assert 'background-image' not in _rule(landing_css, '.lp-hero')
    assert '--intro-wash' not in landing_css + _TOKENS.read_text(encoding='utf-8')


def test_the_hero_title_uses_the_neutral_preset_foreground_in_both_themes():
    """The headline uses the preset foreground without private stop tokens."""
    css = _TOKENS.read_text(encoding='utf-8')
    landing = Path('portfolio_app/static/css/landing.css').read_text(encoding='utf-8')
    title = re.search(r'\.lp-hero \.lp-title\s*\{([^}]*)\}', landing)
    assert title and 'color: var(--foreground)' in title.group(1)
    assert '--hero-title-' not in css + landing


def test_landing_sample_data_is_internally_consistent():
    """Public preview uses exact server calculations, including dividends once."""
    script = _landing_script()
    sample = OverviewService.get_landing_preview()
    metrics = sample['metrics']
    assert len(sample['portfolios']) == 3
    assert sum(p['bookValue'] for p in sample['portfolios']) == metrics['book_value'] == D('42180')
    assert metrics['net_contributions'] == D('36130')
    assert metrics['total_realized_earnings'] == D('6050')
    assert metrics['paid_in_capital'] == D('48000')
    assert metrics['capital_return'] == expected_percent('6050', '48000')
    assert metrics['cash_balance'] == D('6320')
    assert metrics['dividend_income'] == D('2410')
    assert metrics['book_value'] == metrics['net_contributions'] + metrics['total_realized_earnings']
    assert 'function total(' in script
    assert "total('bookValue')" in script
    assert 'renderMetrics' not in script
    assert 'realizedTradingReturn' not in script

    for stale in ('Gold', 'Bonds', 'landingBookValueChart', 'landingCapitalChart'):
        assert stale not in script


def test_landing_links_anchors_and_removed_terms(app):
    html = _landing_html(app)
    text = _visible_text(html)
    lower_text = text.lower()

    assert 'href="/login"' in html
    assert 'href="/register"' not in html
    header = re.search(r'<header class="lp-nav">(.*?)</header>', html, re.DOTALL)
    assert header
    assert '>Get Started</a>' in header.group(1)
    assert '>Continue</a>' not in header.group(1)

    # Every in-page anchor must resolve to a section that actually exists.
    anchors = set(re.findall(r'href="#([\w-]+)"', html))
    assert anchors
    for anchor in anchors:
        assert f'id="{anchor}"' in html

    assert 'Manual by Design' in text
    assert 'No Market Feeds' in text
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
        user.password_hash = 'legacy-test-hash'
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    authenticate_client(client, user_id)

    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'A clear record of every portfolio you manage.' not in html
    assert 'Overview' in _visible_text(html)
