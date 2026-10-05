"""Static contracts for the finalized Assets presentation and pagination."""

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
    assert 'symbol-card surface-card surface-interactive' in ASSETS
    assert 'disclosure__toggle surface-interactive__control' in ASSETS
    assert "{{ icon('chevron-right', class='disclosure__chevron') }}" in ASSETS
    assert 'badge badge--secondary' in ASSETS
    assert 'disclosure__metrics disclosure__metrics--assets' in ASSETS
    assert 'style="--metric-columns:7"' not in ASSETS

    expected = (
        ("metric('Entries')", 'item.summary.transaction_count + symbol_dividends|length'),
        ("metric('Total Spent')", 'money(item.summary.total_buy_cost)'),
        ("metric('Quantity')", 'quantity(item.summary.total_quantity_held)'),
        ("metric('Average Cost')", 'money(item.summary.average_cost'),
        ("metric('Realized P&L')", "money(item.summary.realized_pnl, tone='sign', signed=true)"),
        ("metric('Realized Trading Return',", 'percent(item.summary.return_percent'),
        ("metric('Income')", "money(symbol_dividend_total, tone='income', signed=true)"),
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


def test_transaction_and_income_rows_share_financial_table_contract():
    assert 'table records-table records-table--asset-entries' in ASSETS
    assert 'Entries for {{ item.symbol }} in {{ item.portfolio.name }}' in ASSETS
    assert '>Total Amount</th>' in ASSETS
    assert '{{ record_type(transaction.transaction_type) }}' in ASSETS
    assert "{{ record_type('Income') }}" in ASSETS
    assert 'money(financial.cash_amount)' in ASSETS
    assert "money(financial.realized_trading_pnl, tone='sign', signed=true)" in ASSETS
    assert "money(div.amount, tone='income')" in ASSETS
    assert 'class="small records-cell' not in ASSETS
    assert 'table-light' not in ASSETS
    assert 'table-hover' not in ASSETS

    hover = _rule(COMPONENTS_CSS, '.table tbody tr:hover > *')
    assert 'background-color: var(--muted-half)' in hover
    assert not re.search(r'financial-|chart-|destructive', hover)


def test_asset_actions_use_short_remove_controls_and_explicit_dialog_titles():
    assert ASSETS.count('<span>Remove</span>') == 3
    assert ASSETS.count("{{ icon('trash') }}Remove") == 3
    for forbidden in ('Remove Asset</span>', 'Remove Entry</span>', 'Remove Income</span>'):
        assert forbidden not in ASSETS
    for title in ('Remove Asset Entry', 'Remove Asset', 'Remove Income'):
        assert title in ASSETS
    assert ASSETS.count('dropdown-item--danger') == 3
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
    assert 'id="total_cost_preview" class="tx-preview" aria-live="polite"' in ASSETS
    assert 'id="edit_total_cost_preview" class="tx-preview" aria-live="polite"' in ASSETS
    assert "const total = isSell ? (gross - fees) : (gross + fees);" in MAIN_JS
    assert "const label = isSell ? 'Total Received:' : 'Total Spent:';" in MAIN_JS


def test_assets_copy_and_empty_state_follow_scoped_title_case():
    for label in (
        'All Portfolios', 'Search Asset', 'Add Asset', 'Add Entry',
        'Add Income', 'Average Cost', 'Realized Trading Return', 'Total Amount',
        'Total Spent', 'Total Received', 'Notes (Optional)',
        'Price (Per Unit)', 'No Assets Yet', 'Create Portfolio First',
        'Save Changes',
    ):
        assert label in ASSETS + MAIN_JS
    for legacy in (
        'Notes (optional)', 'Price (per unit)', 'Create A Portfolio First',
        'Confirm Remove',
    ):
        assert legacy not in ASSETS
    assert "empty_state('square-plus', 'No Assets Yet'" in ASSETS


def test_shared_pagination_uses_native_buttons_and_tabler_icons():
    assert 'const Pagination = {' in MAIN_JS
    assert "document.createElement('button')" in MAIN_JS
    assert "button.type = 'button'" in MAIN_JS
    assert "button.setAttribute('aria-current', 'page')" in MAIN_JS
    assert 'button.disabled = disabled' in MAIN_JS
    assert "window.OnePortfolioIcons.create(icon)" in MAIN_JS
    assert "icon: 'chevron-left'" in MAIN_JS
    assert "icon: 'chevron-right'" in MAIN_JS
    assert "label: 'Previous Page'" in MAIN_JS
    assert "label: 'Next Page'" in MAIN_JS

    for source in (ASSETS, PORTFOLIOS):
        assert 'window.OnePortfolioPagination.render' in source
        assert 'class="pagination-bar"' in source
        for obsolete in (
            'tx-pagination-bar', 'tx-pg-num', 'tx-pg-indicator',
            '&#8249;', '&#8250;', 'outer-pg-prev', 'outer-pg-next',
        ):
            assert obsolete not in source


def test_pagination_css_is_one_canonical_token_driven_contract():
    section = COMPONENTS_CSS.split('12. PAGINATION', 1)[1].split(
        '13. EMPTY STATES', 1
    )[0]
    for selector in (
        '.pagination-bar', '.pagination', '.pagination__control',
        '.pagination__control[aria-current="page"]',
        '.pagination__control:disabled',
    ):
        assert selector in section
    assert 'var(--accent)' in section
    assert 'var(--accent-foreground)' in section
    assert 'var(--muted-foreground)' in section
    assert 'var(--radius-lg)' in section
    assert '--fg-' not in section
    assert '--bg-' not in section
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', section, re.I)


def test_assets_scope_has_no_chart_palette_or_raw_component_colors():
    assert '--portfolio-chart-' not in ASSETS
    assert '--chart-' not in ASSETS
    assert 'bi-' not in ASSETS
    assert not re.search(r'(?<!&)#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', ASSETS, re.I)
