"""Static contracts for grouped Assets presentation and unrestricted records."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (ROOT / 'portfolio_app' / 'templates' / 'assets.html').read_text(
    encoding='utf-8'
)
PORTFOLIOS = (
    ROOT / 'portfolio_app' / 'templates' / 'portfolios.html'
).read_text(encoding='utf-8')
APP_CSS = (ROOT / 'portfolio_app' / 'static' / 'css' / 'app.css').read_text(
    encoding='utf-8'
)
COMPONENTS_CSS = (
    ROOT / 'portfolio_app' / 'static' / 'css' / 'components.css'
).read_text(encoding='utf-8')
MAIN_JS = (ROOT / 'portfolio_app' / 'static' / 'js' / 'main.js').read_text(
    encoding='utf-8'
)


PREVIEW_JS = (ROOT / 'portfolio_app/static/js/transaction_previews.js').read_text(encoding='utf-8')


def _rule(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert match, f'missing rule: {selector}'
    return match.group(1)


def test_page_controls_keep_shared_nova_and_filter_contracts():
    assert '{% block page_title %}Assets{% endblock %}' in ASSETS
    assert 'class="btn btn-outline-secondary filter-dropdown-btn"' in ASSETS
    assert 'class="filter-dropdown-btn__label"' in ASSETS
    assert "selected_portfolio or 'All Portfolios'" in ASSETS
    assert 'id="symbolSearch"' in ASSETS
    assert 'placeholder="Search Asset…"' in ASSETS
    assert 'class="btn btn-primary js-add-symbol-btn"' in ASSETS
    assert "{{ icon('filter') }}" in ASSETS
    assert "{{ icon('search') }}" in ASSETS
    assert "{{ icon('plus') }}" in ASSETS

    label = _rule(COMPONENTS_CSS, '.filter-dropdown-btn__label')
    assert 'text-overflow: ellipsis' in label
    assert 'white-space: nowrap' in label


def test_asset_disclosures_preserve_metrics_formatters_and_neutral_identity():
    assert 'class="disclosure enter" aria-label="Asset List"' in ASSETS
    assert 'symbol-card surface-card' in ASSETS
    assert 'disclosure__toggle' in ASSETS
    assert "{{ icon('chevron-right', class='disclosure__chevron') }}" in ASSETS
    assert 'badge badge--secondary' in ASSETS
    assert 'data-summary-list="assets"' in ASSETS
    assert 'role="listitem"' in ASSETS
    assert 'summary_header(' in ASSETS
    assert 'disclosure__metrics' in ASSETS
    assert 'style="--metric-columns:7"' not in ASSETS

    expected = (
        ("metric('Entries')", 'item.summary.transaction_count + symbol_dividends|length'),
        ("metric('Purchase Cost')", 'money(item.summary.total_purchase_cost)'),
        ("metric('Quantity')", 'quantity(item.summary.total_quantity_held)'),
        ("metric('Avg. Cost')", 'money(item.summary.average_unit_cost'),
        ("metric('Cumulative P&L')", "money(item.summary.total_realized_earnings, tone='sign', signed=true)"),
        ("metric('Return')", 'percent(item.summary.purchase_cost_return'),
        ("metric('Dividends')", "money(symbol_dividend_total, tone='income', signed=true)"),
    )
    positions = []
    for label, formatter in expected:
        assert label in ASSETS
        assert formatter in ASSETS
        positions.append(ASSETS.index(label))
    assert positions == sorted(positions)

    badge = _rule(COMPONENTS_CSS, '.badge--secondary')
    assert 'var(--secondary)' in badge
    assert 'var(--secondary-foreground)' in badge
    assert '--chart-' not in badge
    assert '--financial-' not in badge
    identity = _rule(APP_CSS, '.disclosure__identity > .badge')
    assert 'color-mix(in oklab, var(--secondary) 95%, var(--foreground))' in identity
    assert 'font-size: 0.625rem' in identity and 'font-weight:' not in identity
    assert 'font-size: var(--text-sm)' in _rule(APP_CSS, '.disclosure__name')


def test_asset_groups_use_card_surfaces_and_distinct_summary_states():
    row = _rule(COMPONENTS_CSS, '.card,\n  .panel,\n  .surface-card,\n  .surface-table')
    assert 'border: 0' in row
    assert 'background-color: var(--card)' in row
    assert 'border-radius: var(--radius-xl)' in row
    assert 'box-shadow: 0 0 0 1px var(--surface-ring)' in row
    assert '.disclosure__item:not([hidden]) ~ .disclosure__item:not([hidden])' not in APP_CSS
    assert 'gap: var(--space-3)' in _rule(APP_CSS, '.summary-list__items')
    assert 'background-color: var(--muted-half)' in _rule(APP_CSS, '.disclosure__head')
    focus = _rule(APP_CSS, '.disclosure__toggle:focus-visible')
    assert 'outline: 2px solid var(--ring)' in focus
    assert 'box-shadow: none' in focus
    expanded = _rule(APP_CSS, '.disclosure__item .disclosure__head:has([aria-expanded="true"])')
    assert 'background-color: var(--muted)' in expanded
    text_state = _rule(APP_CSS, '.disclosure__item .disclosure__head:has([aria-expanded="true"]) .disclosure__toggle')
    assert '--muted-foreground: var(--accent-foreground)' in text_state
    assert '--financial-flat: var(--accent-foreground)' in text_state
    assert '--muted-foreground:' not in expanded  # Action menus retain their own text roles.
    assert 'border-top: 1px solid var(--border)' in _rule(APP_CSS, '.disclosure__panel')
    assert 'background-color' not in _rule(APP_CSS, '.disclosure__panel')
    # The same row contract serves both lists; page-wide empty states stay cards.
    assert 'portfolio-card surface-card' in PORTFOLIOS
    assert "empty_state('square-plus', 'No Assets Yet'" in ASSETS


def test_transaction_and_income_rows_share_financial_table_contract():
    assert 'table records-table' in ASSETS
    assert 'Entries for {{ item.symbol }} in {{ item.portfolio.name }}' in ASSETS
    assert '>Total Amount</th>' in ASSETS
    # Entry results remain explicitly trading-only, unlike dividend-inclusive summaries.
    assert '<th scope="col" class="records-cell records-cell--number" aria-label="Return" title="Return">Return</th>' in ASSETS
    assert '>Realized Return</th>' not in ASSETS
    assert "metric('Return')" in ASSETS
    assert 'percent(financial.realized_trading_return)' in ASSETS
    assert '{{ record_type(transaction.transaction_type) }}' in ASSETS
    assert "{{ record_type('Dividends') }}" in ASSETS
    assert 'money(financial.transaction_amount)' in ASSETS
    assert "money(financial.realized_trading_pnl, tone='sign', signed=true)" in ASSETS
    assert "money(div.amount, tone='income')" in ASSETS
    assert 'class="small records-cell' not in ASSETS
    assert 'table-light' not in ASSETS
    assert 'table-hover' not in ASSETS

    hover = _rule(COMPONENTS_CSS, '.table tbody tr:hover > *')
    assert 'background-color: var(--muted-half)' in hover
    assert not re.search(r'financial-|chart-|destructive', hover)


def test_asset_actions_use_short_remove_controls_and_explicit_dialog_titles():
    assert ASSETS.count('<span>Remove</span>') == 1
    assert ASSETS.count("{{ icon('trash') }}Remove") == 3
    for forbidden in ('Remove Asset</span>', 'Remove Entry</span>', 'Remove Dividends</span>'):
        assert forbidden not in ASSETS
    for title in ('Remove Asset Entry', 'Remove Asset', 'Remove Dividends'):
        assert title in ASSETS
    assert ASSETS.count('dropdown-item--danger') == 1
    assert ASSETS.count('class="btn btn-danger"') == 3


def test_asset_dialogs_keep_forms_fields_and_transaction_semantics():
    for form_contract in (
        "url_for('transactions.symbol_add')",
        "url_for('transactions.transaction_add')",
        'id="editTransactionForm"',
        'id="deleteTransactionForm"',
        'id="deleteSymbolForm"',
        "url_for('transactions.dividend_add')",
        'id="editDividendForm"',
        'id="deleteDividendForm"',
    ):
        assert form_contract in ASSETS
    assert ASSETS.count('name="csrf_token"') == 8
    for name in (
        'symbol_portfolio_id', 'symbol_ticker', 'portfolio_id',
        'transaction_type', 'symbol', 'price', 'quantity', 'fees', 'date',
        'notes', 'edit_price', 'edit_quantity', 'edit_fees', 'edit_date',
        'edit_notes', 'amount', 'edit_amount',
    ):
        assert f'name="{name}"' in ASSETS

    assert '<option value="Buy">Buy</option>' in ASSETS
    assert '<option value="Sell">Sell</option>' in ASSETS
    assert 'class="tx-type-tab tx-tab-buy"' in ASSETS
    assert 'class="tx-type-tab tx-tab-sell"' in ASSETS
    assert 'id="transaction_amount_preview" class="tx-preview" aria-live="polite"' in ASSETS
    assert 'id="edit_transaction_amount_preview" class="tx-preview" aria-live="polite"' in ASSETS
    assert "'Net Proceeds:' : 'Purchase Cost:'" in PREVIEW_JS


def test_assets_copy_and_empty_state_follow_scoped_title_case():
    for label in (
        'All Portfolios', 'Search Asset', 'Add Asset', 'Add Entry',
        'Add Dividends', 'Avg. Cost', 'Return', 'Total Amount',
        'Purchase Cost', 'Net Proceeds', 'Notes (Optional)',
        'Price (Per Unit)', 'No Assets Yet', 'Create Portfolio First',
        'Save Changes',
    ):
        assert label in ASSETS + MAIN_JS + PREVIEW_JS
    for legacy in (
        'Notes (optional)', 'Price (per unit)', 'Create A Portfolio First',
        'Confirm Remove',
    ):
        assert legacy not in ASSETS
    assert "empty_state('square-plus', 'No Assets Yet'" in ASSETS


def test_grouped_lists_have_no_pagination_or_hidden_page_caps():
    shared = (ROOT / 'portfolio_app/static/js/summary_lists.js').read_text(encoding='utf-8')
    for source in (ASSETS, PORTFOLIOS, shared, MAIN_JS):
        assert 'OnePortfolioPagination' not in source
        assert 'pagination-bar' not in source
        assert 'PAGE_SIZE' not in source
        assert 'pageSize' not in source
    assert '.pagination' not in COMPONENTS_CSS
    assert '.surface-row' not in COMPONENTS_CSS
    assert 'setupAssetSearch' in ASSETS


def test_assets_scope_has_no_chart_palette_or_raw_component_colors():
    assert '--portfolio-chart-' not in ASSETS
    assert '--chart-' not in ASSETS
    assert 'bi-' not in ASSETS
    assert not re.search(r'(?<!&)#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', ASSETS, re.I)
