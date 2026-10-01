"""Final public Landing presentation and product-parity contracts."""

from pathlib import Path
import re


ROOT = Path('portfolio_app')
TEMPLATE = (ROOT / 'templates/landing.html').read_text(encoding='utf-8')
CSS = (ROOT / 'static/css/landing.css').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static/js/landing.js').read_text(encoding='utf-8')
FORMATTERS = (ROOT / 'static/js/display_formatters.js').read_text(encoding='utf-8')
BASE = (ROOT / 'templates/base.html').read_text(encoding='utf-8')


def _rule(source, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', source)
    assert match, f'missing rule: {selector}'
    return match.group(1)


def test_public_shell_reuses_logo_theme_typography_and_icon_contracts():
    assert "include 'components/logo_mark.html'" in TEMPLATE
    assert 'family=Geist:wght@400;500;600' in TEMPLATE
    assert "include 'components/icon_sprite.html'" in TEMPLATE
    assert "from 'macros/icons.html' import icon" in TEMPLATE

    toggle = 'class="icon-button theme-toggle" data-theme-toggle'
    assert toggle in TEMPLATE and toggle in BASE
    for name in ('moon', 'sun'):
        icon = f"icon('{name}', class='theme-icon theme-icon--{name}')"
        assert icon in TEMPLATE and icon in BASE
    assert 'bi-' not in TEMPLATE
    assert '<svg' not in TEMPLATE
    assert '.theme-toggle' not in CSS


def test_header_and_ctas_use_native_navigation_and_shared_buttons():
    assert '<nav class="lp-nav__links" aria-label="Sections">' in TEMPLATE
    assert '<nav class="lp-footer__links" aria-label="Footer">' in TEMPLATE
    assert TEMPLATE.count("href=\"{{ url_for('auth.login') }}\"") == 4
    assert TEMPLATE.count('class="btn btn-primary') == 3
    assert 'Get Started' in TEMPLATE
    assert TEMPLATE.count('Create Portfolio') == 2
    assert 'Get started' not in TEMPLATE
    assert 'Create your portfolio' not in TEMPLATE

    nav_link = _rule(CSS, '.lp-nav__links a')
    nav_hover = _rule(CSS, '.lp-nav__links a:hover')
    assert 'var(--muted-foreground)' in nav_link
    assert 'var(--accent)' in nav_hover
    assert 'var(--accent-foreground)' in nav_hover
    assert '.lp-nav__links a::after' not in CSS


def test_preview_composes_authenticated_overview_contracts():
    assert 'class="lp-shot surface-card"' in TEMPLATE
    assert 'lp-shot__chrome' not in TEMPLATE + CSS
    assert TEMPLATE.count('fact supporting-item') == 4
    assert 'Book Value' in TEMPLATE
    assert 'Total Capital' in TEMPLATE
    assert 'Total Cash' in TEMPLATE
    assert 'Total Income' in TEMPLATE
    assert 'Realized P&amp;L' in TEMPLATE
    assert 'num--income' in TEMPLATE
    assert 'num--pos' in TEMPLATE
    assert 'class="allocation-legend"' in TEMPLATE
    assert 'landingLegend landingChartStatus' in TEMPLATE
    assert 'id="landingChartStatus" aria-live="polite"' in TEMPLATE
    assert "row.className = 'allocation-legend__row'" in SCRIPT
    for class_name in ('name', 'value', 'pct'):
        assert f"className = '{class_name}'" in SCRIPT


def test_preview_uses_one_formatter_palette_and_accessible_text_status():
    assert 'window.OnePortfolioDisplay' in SCRIPT
    assert 'new Intl.NumberFormat' not in SCRIPT
    assert "new Intl.NumberFormat('en-US'" in FORMATTERS
    assert "filename='js/display_formatters.js'" in TEMPLATE
    assert "['--portfolio-chart-1', '--portfolio-chart-2', '--portfolio-chart-3']" in SCRIPT
    assert '--chart-6' not in SCRIPT
    assert '--chart-7' not in SCRIPT
    assert '--chart-other' not in SCRIPT
    assert "status.textContent = 'Sample allocation: '" in SCRIPT
    assert "display.money(item.bookValue, false)" in SCRIPT
    assert "display.percentage(shares[index], 1, false)" in SCRIPT


def test_landing_css_uses_canonical_roles_and_layout_only():
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:rgba?|oklch)\(', CSS, re.I)
    assert not re.search(
        r'var\(--(?:bg-|fg-|line-|brand(?:-|\)))',
        CSS,
    )
    for role in (
        '--background', '--foreground', '--card', '--muted',
        '--muted-foreground', '--border', '--accent',
    ):
        assert f'var({role})' in CSS
    assert '--portfolio-chart-' not in CSS
    assert '--financial-' not in CSS


def test_informational_cards_are_shared_neutral_noninteractive_surfaces():
    assert 'class="lp-card surface-card"' in TEMPLATE
    card = _rule(CSS, '.lp-card')
    icon = _rule(CSS, '.lp-card__icon')
    for edge in ('border:', 'border-radius:', 'background-color:', 'box-shadow:'):
        assert edge not in card
    assert 'background-color: var(--muted)' in icon
    assert 'color: var(--foreground)' in icon
    assert '.lp-card:hover' not in CSS
    assert '.lp-card::before' not in CSS


def test_copy_is_title_case_and_avoids_unsupported_claims():
    expected = (
        'How It Works', 'What It Isn’t', 'Manual by Design',
        'Cash Stays Visible', 'Average Cost, Done Properly',
        'Book Value, Not Guesswork', 'Create Your Portfolios',
        'Record as You Go', 'Read the Results',
        'Start With Your Own Numbers',
    )
    for text in expected:
        assert text in TEMPLATE

    stale = (
        'How it works', "What it isn't", 'Manual by design',
        'Average cost, done properly', 'under five minutes',
        'takes a few seconds', 'real-time', 'broker integration',
        'automatic synchronization', 'OAuth',
    )
    for text in stale:
        assert text not in TEMPLATE


def test_landing_remains_synthetic_and_has_no_private_data_path():
    combined = TEMPLATE + SCRIPT
    for forbidden in (
        'current_user', 'portfolio_summary', 'allocationData',
        'fetch(', 'XMLHttpRequest', '/api/', 'sessionStorage',
    ):
        assert forbidden not in combined
    assert 'var SAMPLE = {' in SCRIPT
    assert "total('bookValue')" in SCRIPT
    assert "total('capital')" in SCRIPT


def test_responsive_contracts_prevent_fixed_width_overflow():
    shell = _rule(CSS, '.lp-shell')
    grid = _rule(CSS, '.lp-hero__grid')
    split = _rule(CSS, '.lp-shot__split')
    assert 'width: 100%' in shell
    assert 'minmax(0, 1fr)' in grid
    assert 'minmax(0, 1fr)' in split
    assert '.lp-hero__grid > * { min-width: 0; }' in CSS
    for breakpoint in ('64rem', '56rem', '48rem', '36rem', '30rem'):
        assert f'max-width: {breakpoint}' in CSS
