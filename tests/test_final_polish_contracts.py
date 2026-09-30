"""Durable contracts for the final UI-foundation presentation polish."""

import re
from pathlib import Path


ROOT = Path('portfolio_app')
COMPONENTS = (ROOT / 'static/css/components.css').read_text(encoding='utf-8')
ASSETS = (ROOT / 'templates/assets.html').read_text(encoding='utf-8')
BASE = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
LANDING_TEMPLATE = (ROOT / 'templates/landing.html').read_text(encoding='utf-8')
MAIN = (ROOT / 'static/js/main.js').read_text(encoding='utf-8')
LANDING = (ROOT / 'static/js/landing.js').read_text(encoding='utf-8')
OVERVIEW = (ROOT / 'static/js/overview_charts.js').read_text(encoding='utf-8')
FORMATTERS = (ROOT / 'static/js/display_formatters.js').read_text(encoding='utf-8')


def _rule(source, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', source)
    assert match, f'missing rule for {selector}'
    return match.group(1)


def test_calculated_transaction_summary_has_one_neutral_shared_contract():
    assert ASSETS.count('class="tx-preview" aria-live="polite"') == 2
    assert "const label = isSell ? 'Total Received:' : 'Total Spent:';" in MAIN
    assert 'class="tx-preview__label"' in MAIN
    assert 'class="tx-preview__value"' in MAIN

    summary = _rule(COMPONENTS, '.tx-preview')
    label = _rule(COMPONENTS, '.tx-preview__label')
    value = _rule(COMPONENTS, '.tx-preview__value')
    assert 'margin-top: var(--space-2)' in summary
    assert 'font-size: var(--text-sm)' in summary
    assert 'color: var(--muted-foreground)' in label
    assert 'color: var(--foreground)' in value
    assert 'font-variant-numeric: tabular-nums' in value

    contract = summary + label + value
    assert not re.search(r'--financial-|--portfolio-chart-|#[0-9a-f]{3,8}\b', contract, re.I)
    for edge in ('border:', 'background:', 'box-shadow:'):
        assert edge not in contract


def test_transaction_total_calculation_and_formatting_contract_are_unchanged():
    assert 'const gross = price * quantity;' in MAIN
    assert 'const total = isSell ? (gross - fees) : (gross + fees);' in MAIN
    assert 'const formatted = Utils.formatMoney(total);' in MAIN
    assert 'return window.OnePortfolioDisplay.money(value, false);' in MAIN


def test_browser_display_formatter_is_shared_and_matches_preview_precision():
    assert "new Intl.NumberFormat('en-US'" in FORMATTERS
    assert 'minimumFractionDigits: 2' in FORMATTERS
    assert 'maximumFractionDigits: 2' in FORMATTERS
    assert "number.toFixed(precision) + '%'" in FORMATTERS

    for template in (BASE, LANDING_TEMPLATE):
        assert "filename='js/display_formatters.js'" in template

    for script in (MAIN, LANDING, OVERVIEW):
        assert 'window.OnePortfolioDisplay' in script
        assert 'new Intl.NumberFormat' not in script

    assert "display.percentage(returnPercent, 2, true)" in LANDING
    assert "display.percentage(shares[index], 1, false)" in LANDING
    assert "display.percentage(share, 1, false)" in OVERVIEW


def test_landing_and_overview_share_structured_allocation_legend_contract():
    assert "row.className = 'allocation-legend__row';" in LANDING
    assert (
        "toggle.className = 'allocation-legend__row allocation-legend__toggle';"
        in OVERVIEW
    )
    for script in (LANDING, OVERVIEW):
        assert "className = 'name'" in script
        assert "className = 'value'" in script
        assert "className = 'pct'" in script
        assert 'append(swatch, ' in script

    row = _rule(COMPONENTS, '.allocation-legend__row')
    value = _rule(COMPONENTS, '.allocation-legend .value')
    pct = _rule(COMPONENTS, '.allocation-legend .pct')
    assert 'display: grid' in row
    assert 'grid-template-columns:' in row
    assert 'gap:' in row
    assert 'text-align: right' in value
    assert 'text-align: right' in pct
    assert 'font-variant-numeric: tabular-nums' in value + pct


def test_landing_sample_book_value_and_percentages_are_consistent():
    values = [float(value) for value in re.findall(r'bookValue:\s*(\d+)', LANDING)]
    assert values == [18400.0, 14200.0, 9580.0]
    assert sum(values) == 42180.0
    shares = [value / sum(values) * 100 for value in values]
    assert round(sum(shares), 10) == 100.0
    assert sum(round(value, 1) for value in shares) == 100.0

    assert "bookValue: display.money(total('bookValue'), false)" in LANDING
    assert 'var grandTotal = total(\'bookValue\');' in LANDING
    assert '(item.bookValue / grandTotal) * 100' in LANDING
    assert 'data: shares' in LANDING
    assert 'value.textContent = display.money(item.bookValue, false);' in LANDING


def test_landing_preview_reuses_overview_metric_and_visualization_roles():
    assert LANDING_TEMPLATE.count('fact supporting-item') == 4
    assert LANDING_TEMPLATE.count('supporting-item__label') == 4
    assert LANDING_TEMPLATE.count('supporting-item__value') == 4
    assert 'num--income' in LANDING_TEMPLATE
    assert 'num--pos' in LANDING_TEMPLATE

    for script in (LANDING, OVERVIEW):
        assert "cssVar('--card')" in script
        assert '--portfolio-chart-' in script
        assert '--chart-6' not in script
        assert '--chart-7' not in script
        assert '--chart-other' not in script


def test_landing_preview_remains_synthetic_and_public_only():
    combined = LANDING_TEMPLATE + LANDING
    for private_hook in (
        'fetch(', 'XMLHttpRequest', '/api/', 'current_user.portfolio',
        'portfolio_summary', 'allocationData',
    ):
        assert private_hook not in combined


def test_landing_and_authenticated_shell_share_theme_toggle_contract():
    button = 'class="icon-button theme-toggle" data-theme-toggle'
    assert button in BASE
    assert button in LANDING_TEMPLATE
    for template in (BASE, LANDING_TEMPLATE):
        assert "icon('moon', class='theme-icon theme-icon--moon')" in template
        assert "icon('sun', class='theme-icon theme-icon--sun')" in template

    assert 'bi-moon-stars' not in LANDING_TEMPLATE
    assert "include 'components/icon_sprite.html'" in LANDING_TEMPLATE
    assert "from 'macros/icons.html' import icon" in LANDING_TEMPLATE
