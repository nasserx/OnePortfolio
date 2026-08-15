import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from portfolio_app import db
from portfolio_app.models.user import User
from tests._colour import (
    NON_TEXT_MIN,
    TEXT_MIN,
    composite,
    contrast,
    resolve,
    theme_tokens,
    to_rgb,
)

_TOKENS = Path('portfolio_app/static/css/tokens.css')

# What the hero actually prints, and the floor each needs. The title is 56px
# semibold, so WCAG's large-text floor applies to its two gradient stops; the
# proof icons are the only non-text mark.
HERO_INKS = {
    'fg-default': TEXT_MIN,
    'fg-muted': TEXT_MIN,
    'fg-subtle': NON_TEXT_MIN,
    'hero-title-from': 3.0,
    'hero-title-to': 3.0,
}


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
    """`color-mix(in srgb, var(--bg-canvas) 82%, transparent)` -> 0.82."""
    match = re.fullmatch(
        r'color-mix\(\s*in srgb,\s*var\(\s*--bg-canvas\s*\)\s*'
        r'([\d.]+)%\s*,\s*transparent\s*\)',
        value.strip(),
    )
    assert match is not None, (
        f'expected a --bg-canvas/transparent color-mix, got {value!r}. The '
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


def test_landing_product_card_is_a_solid_surface():
    """The preview is the application, not a window onto anything.

    This card was glass, back when there was a photograph behind it, and the
    transparency made the preview read as a hero treatment rather than as the
    product. There is nothing behind it now, so translucency would only mean
    the intro's gradient bleeding through its figures.

    Pinned as *no translucency mechanism* rather than as a colour, so the
    surfaces can be retinted freely. What may not come back is a fill that
    lets the photograph into the card's type — which is also what let this
    file stop modelling the picture reaching the card at all.
    """
    css = _landing_css()
    card = _rule(css, '.lp-shot')
    chrome = _rule(css, '.lp-shot__chrome')

    for name, rule in (('.lp-shot', card), ('.lp-shot__chrome', chrome)):
        background = rule['background-color']
        assert background.startswith('var(--bg-'), (
            f'{name} is painted with {background!r}; a solid card takes a '
            f'surface role directly'
        )
        assert 'backdrop-filter' not in rule, (
            f'{name} blurs what is behind it, which only means anything if '
            f'something behind it shows through'
        )
        # Flat as well as opaque. The border draws the card's edge; an
        # elevation shadow drew a second, softer one just outside it. Depth
        # was worth paying for when the card floated on a photograph — it
        # sits on the page now, so it is drawn like the page.
        for lifted in ('box-shadow', 'filter'):
            assert lifted not in rule, (
                f'{name} declares {lifted}; the preview card is flat'
            )

    # The token that tuned the glass is gone from the stylesheets entirely,
    # so it cannot come back for this card alone without being noticed.
    assert 'hero-card-fill' not in css, (
        'landing.css references --hero-card-fill again; that token was '
        'deleted with the glass'
    )

    # Nor by a pseudo-element painting a shadow the rule itself does not.
    for pseudo in re.findall(r'\.lp-shot[\w-]*::(?:before|after)[^{]*\{([^}]*)\}', css):
        assert 'box-shadow' not in pseudo, (
            'a .lp-shot pseudo-element paints a shadow; flat means flat'
        )


# ---------------------------------------------------------------------------
# The intro: a gradient and a headline, and nothing else
# ---------------------------------------------------------------------------


def _wash_stops():
    """The colour/percentage pairs inside `--intro-wash`, from tokens.css."""
    css = _TOKENS.read_text(encoding='utf-8')
    block = re.search(r'--intro-wash:(.*?);', css, re.S)
    assert block is not None, '--intro-wash is no longer declared in tokens.css'
    stops = re.findall(
        r'color-mix\(\s*in srgb,\s*var\(\s*(--[\w-]+)\s*\)\s*([\d.]+)%',
        block.group(1),
    )
    assert stops, 'the wash declares no colour-mix stops'
    return stops


def test_landing_intro_carries_no_decorative_media(app):
    """The intro is type on a gradient. There is nothing else in it.

    Every previous version of this section had a layer: a photograph under a
    measured scrim, then a vector composition under a clip. Both are gone,
    and what this pins is that neither can come back quietly — no image, no
    inline art, no element whose only job is decoration. The headline is the
    visual, and the gradient is the whole of the ornament budget.
    """
    html = _landing_html(app)

    for banned in ('/static/img/hero', 'hero-media', 'lp-heroart', '<picture'):
        assert banned not in html, (
            f'the landing intro references {banned!r}; its only background '
            f'treatment is --intro-wash on the section itself'
        )

    # The one canvas on this page is the product preview's allocation ring,
    # which is data rather than decoration.
    assert html.count('<canvas') == 1

    # Scoped to the intro rather than the page: the wordmark in the header is
    # an image and is meant to be. Inside this section, the only graphic is
    # the preview card's ring, which is the product drawing its own data —
    # the ban is on decoration, not on the product.
    start = html.index('<section class="lp-hero">')
    intro = html[start:html.index('</section>', start)]
    for element in ('<img', '<svg', '<picture'):
        assert element not in intro, (
            f'{element}> inside the intro; apart from the preview card the '
            f'section carries type on a gradient and nothing else'
        )

    landing_css = _landing_css()
    assert 'background-image: var(--intro-wash);' in landing_css
    assert '--intro-wash:' not in landing_css, (
        'landing.css restates the wash instead of pointing at the token; the '
        'auth showcase shares it, so there is one owner in tokens.css'
    )


def test_intro_wash_is_shared_by_both_surfaces_from_one_declaration():
    """One gradient, one owner, two consumers.

    The landing intro and the auth showcase are the same treatment, and they
    stay the same treatment by both reading the same token rather than each
    carrying a copy. A second declaration is the failure this exists to
    catch: the two surfaces would drift a percent at a time and nothing would
    ever go red.
    """
    tokens = _TOKENS.read_text(encoding='utf-8')
    app_css = Path('portfolio_app/static/css/app.css').read_text(encoding='utf-8')

    assert tokens.count('--intro-wash:') == 1, (
        'the wash is declared more than once; it is theme-agnostic by '
        'construction and must not be overridden per theme'
    )
    assert 'background-image: var(--intro-wash);' in app_css, (
        'the auth showcase no longer shares the intro wash'
    )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_intro_wash_keeps_every_ink_printed_on_it_legible(theme):
    """The wash sits under type, so it is checked against every ink.

    A photograph needed sampling because the background under a word was
    whatever the picture happened to be doing there. This is known stops at
    known alpha over a known canvas, so the check is exact — and it runs
    against the *strongest* stop regardless of where that stop falls, so
    re-centring the gradient later cannot slide a heavier colour under the
    heading without failing here.
    """
    declared = theme_tokens(_TOKENS.read_text(encoding='utf-8'), theme)
    canvas = to_rgb(resolve('bg-canvas', declared))

    failures = []
    for role, floor in HERO_INKS.items():
        ink = resolve(role, declared)
        for token, percent in _wash_stops():
            veil = (to_rgb(resolve(token.lstrip('-'), declared)),
                    float(percent) / 100)
            ratio = contrast(ink, composite(canvas, veil))
            if ratio < floor:
                failures.append(
                    f'{theme}: --{role} over {token} at {percent}% falls to '
                    f'{ratio:.2f}:1, needs {floor}:1'
                )

    assert not failures, 'intro wash legibility:\n  ' + '\n  '.join(failures)


def test_intro_wash_stays_a_wash():
    """Restrained is part of the contract, not a matter of taste.

    Everything on these surfaces is read against the canvas plus one of these
    stops. Keeping them in single digits is what lets the copy use ordinary
    roles with no step-ups anywhere, which is the simplification the
    photograph never allowed.
    """
    for token, percent in _wash_stops():
        assert float(percent) <= 12, (
            f'--intro-wash mixes {token} at {percent}%; past about a tenth '
            f'this stops being a wash and starts being a surface that type '
            f'has to be checked against case by case'
        )


def test_the_hero_title_is_a_cobalt_violet_gradient_in_both_themes():
    """The headline carries the intro, and it does it the same way in both.

    Two semantic roles rather than raw ramp steps, which is the whole reason
    one declaration serves light and dark: `--income` and `--brand` already
    resolve to a deep pair against cream and a bright pair against near
    black. A theme block that pins either end is the regression here — it
    would mean the gradient had stopped being one decision.
    """
    css = _TOKENS.read_text(encoding='utf-8')
    stops = ('hero-title-from', 'hero-title-to')

    for theme in ('light', 'dark'):
        declared = theme_tokens(css, theme)
        ends = [resolve(stop, declared) for stop in stops]
        assert ends[0] != ends[1], (
            f'{theme}: both title stops resolve to {ends[0]}; a gradient with '
            f'one colour is a flat fill, and this heading is meant to ramp'
        )
        for stop, end in zip(stops, ends):
            assert end != resolve('fg-default', declared), (
                f'{theme}: --{stop} collapsed onto --fg-default. The headline '
                f'is the one piece of brand colour on this page that is not a '
                f'control; losing it is a design change, not a tidy-up.'
            )

    # Declared once, in the light block, and never overridden per theme.
    for stop in stops:
        assert css.count(f'--{stop}:') == 1, (
            f'--{stop} is declared more than once; both ends are semantic '
            f'roles precisely so the theme blocks need say nothing about them'
        )


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
