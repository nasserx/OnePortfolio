"""Static contracts for the finalized authenticated Overview presentation."""

from pathlib import Path
import re


ROOT = Path('portfolio_app')
TEMPLATE = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
MACROS = (ROOT / 'templates/macros/ui.html').read_text(encoding='utf-8')
APP = (ROOT / 'static/css/app.css').read_text(encoding='utf-8')
COMPONENTS = (ROOT / 'static/css/components.css').read_text(encoding='utf-8')
CHART = (ROOT / 'static/js/overview_charts.js').read_text(encoding='utf-8')


def _rule(source, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', source)
    assert match, f'missing rule for {selector}'
    return match.group(1)


def test_overview_keeps_the_approved_information_hierarchy():
    positions = [
        TEMPLATE.index('id="overview-headline"'),
        TEMPLATE.index('class="hero-figure__facts"'),
        TEMPLATE.index('class="card alloc-panel"'),
        TEMPLATE.index('class="overview-ledger enter"'),
    ]
    assert positions == sorted(positions)
    assert '<h2 class="hero-figure__label" id="overview-headline">' in TEMPLATE
    assert '<h2 class="panel__title overview-ledger__title" id="portfolios-title">' in TEMPLATE


def test_book_value_and_supporting_metric_contracts_are_preserved():
    assert 'Book Value' in TEMPLATE
    assert 'totals.total_value|fmt_display_money' in TEMPLATE
    assert 'totals.return_percent|fmt_display_percent(signed=True)' in TEMPLATE

    labels = re.findall(r"call fact\('([^']+)'", TEMPLATE)
    assert labels == ['Total Capital', 'Total Cash', 'Total Income', 'Realized P&L']
    assert "money(totals.total_capital)" in TEMPLATE
    assert "money(totals.total_cash)" in TEMPLATE
    assert "money(totals.total_income, tone='income', signed=true)" in TEMPLATE
    assert "money(totals.realized_pnl, tone='sign', signed=true)" in TEMPLATE
    assert 'class="fact supporting-item"' in MACROS

    item = _rule(COMPONENTS, '.supporting-item')
    assert 'border: 1px solid var(--border)' in item
    assert 'background-color: transparent' in item
    assert 'box-shadow: none' in item
    assert not re.search(r'--financial-|--(?:portfolio-)?chart-', item)


def test_allocation_chart_and_shared_legend_keep_strict_role_boundaries():
    assert "cssVar('--portfolio-chart-' + i)" in CHART
    for index in range(1, 6):
        assert f'var(--portfolio-chart-{index})' in COMPONENTS
    assert '--financial-' not in CHART
    assert not re.search(r'--chart-(?:[1-9]|other)', CHART)

    assert "toggle.className = 'allocation-legend__row allocation-legend__toggle'" in CHART
    for semantic_part in ('name', 'value', 'pct'):
        assert f"className = '{semantic_part}'" in CHART
    assert 'toggle.append(swatch, label, value, pct)' in CHART

    marker = _rule(COMPONENTS, '.marker')
    assert 'background-color: var(--muted)' in marker
    assert 'color: var(--muted-foreground)' in marker
    assert 'chart-' not in marker


def test_chart_switcher_is_the_shared_neutral_segmented_control():
    assert 'class="segmented" role="tablist"' in TEMPLATE
    assert TEMPLATE.count('class="segmented__option"') == 2
    assert 'By Book Value' in TEMPLATE
    assert 'By Capital' in TEMPLATE

    track = _rule(COMPONENTS, '.segmented')
    option = _rule(COMPONENTS, '.segmented__option')
    selected = _rule(COMPONENTS, '.segmented__option[aria-selected="true"]')
    contract = track + option + selected
    assert 'background-color: var(--muted)' in track
    assert 'color: var(--foreground)' in selected
    assert not re.search(r'--financial-|--(?:portfolio-)?chart-', contract)


def test_portfolio_ledger_uses_neutral_shared_table_semantics():
    assert 'class="ledger surface-table" role="table"' in TEMPLATE
    assert 'class="ledger__row ledger__row--head" role="row"' in TEMPLATE
    assert 'class="ledger__row table-row-interactive" role="row"' in TEMPLATE
    assert 'role="columnheader"' in TEMPLATE
    assert 'class="marker"' in MACROS

    header = _rule(APP, '.ledger__row--head')
    row = _rule(APP, '.ledger__row')
    hover = _rule(COMPONENTS, '.table-row-interactive:is(:hover, :focus-within)')
    number = _rule(APP, '.ledger__num')
    assert 'background-color: transparent' in header
    assert 'color: var(--muted-foreground)' in header
    assert row.count('border-bottom: 1px solid var(--border)') == 1
    assert 'background-color: var(--muted-half)' in hover
    assert 'font-variant-numeric: tabular-nums' in number
    assert 'text-align: right' in number


def test_overview_responsive_and_accessibility_hooks_remain_intact():
    assert 'height: clamp(10rem, 24vw, 12rem)' in _rule(APP, '.alloc-canvas')
    assert '@media (max-width: 60rem)' in APP
    assert '@media (max-width: 32rem)' in APP
    assert 'text-overflow: ellipsis' in _rule(APP, '.ledger__name span:last-child')

    for hook in (
        'role="img"',
        'aria-describedby="allocationLegend allocationChartStatus"',
        'id="allocationChartStatus" aria-live="polite"',
        'role="tablist"',
        'role="tabpanel"',
        'aria-label="View assets in {{ item.name }}"',
    ):
        assert hook in TEMPLATE
    assert "event.key === 'ArrowRight'" in CHART
    assert "event.key === 'ArrowLeft'" in CHART
    assert "event.key === 'Home'" in CHART
    assert "event.key === 'End'" in CHART


def test_empty_state_workflow_and_title_case_copy_are_preserved():
    assert "empty_state('folder-plus', 'No Portfolios Yet'" in TEMPLATE
    assert "url_for('portfolios.portfolios_list')" in TEMPLATE
    assert '<span>Create Portfolio</span>' in TEMPLATE
    assert "? 'Total Capital' : 'Book Value'" in CHART

    for legacy in (
        'Book value', 'Total capital', 'Total cash', 'Total income',
        'Portfolio split', 'By book value', 'By capital', 'View assets',
        'Create portfolio', 'No portfolios yet',
    ):
        assert f'>{legacy}<' not in TEMPLATE
    assert 'text-transform: capitalize' not in TEMPLATE


def test_overview_scope_introduces_no_raw_or_competing_visual_colors():
    overview_css = APP.split('4. OVERVIEW', 1)[1].split('5. DISCLOSURE LIST', 1)[0]
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?|hsla?)\(', overview_css, re.I)
    assert '--portfolio-chart-' not in overview_css
    assert '--financial-' not in overview_css
