"""Static contracts for the finalized Portfolios presentation."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT / 'portfolio_app' / 'templates' / 'portfolios.html'
).read_text(encoding='utf-8')
APP_CSS = (ROOT / 'portfolio_app' / 'static' / 'css' / 'app.css').read_text(
    encoding='utf-8'
)
COMPONENTS_CSS = (
    ROOT / 'portfolio_app' / 'static' / 'css' / 'components.css'
).read_text(encoding='utf-8')


def _rule(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert match, f'missing rule: {selector}'
    return match.group(1)


def test_page_header_action_and_empty_state_keep_shared_workflows():
    assert '{% block page_title %}Portfolios{% endblock %}' in TEMPLATE
    assert 'class="btn btn-primary" data-bs-toggle="modal"' in TEMPLATE
    assert 'data-bs-target="#newPortfolioModal"' in TEMPLATE
    assert "{{ icon('plus') }}" in TEMPLATE
    assert '<span>New Portfolio</span>' in TEMPLATE
    assert "empty_state('folder-plus', 'No Portfolios Yet'" in TEMPLATE
    assert '<span>Create Portfolio</span>' in TEMPLATE


def test_disclosures_keep_behavior_hooks_and_shared_surface_contracts():
    assert 'class="disclosure enter" aria-label="Portfolio List"' in TEMPLATE
    assert 'portfolio-card surface-card surface-interactive' in TEMPLATE
    assert 'disclosure__toggle surface-interactive__control' in TEMPLATE
    assert 'aria-expanded="false" aria-controls="{{ panel_id }}"' in TEMPLATE
    assert 'data-disclosure="{{ item.portfolio.id }}"' in TEMPLATE
    assert "{{ marker(item.portfolio.name) }}" in TEMPLATE
    assert "{{ icon('chevron-right', class='disclosure__chevron') }}" in TEMPLATE
    assert "var SK = 'portfoliosOpen', RK = 'portfoliosOpenRef';" in TEMPLATE

    marker = _rule(COMPONENTS_CSS, '.marker')
    assert '--portfolio-chart-' not in marker
    assert '--chart-' not in marker


def test_existing_summary_metrics_and_formatters_are_preserved():
    expected = (
        ("metric('Entries')", 'item.events|length'),
        ("metric('Total Capital')", 'money(item.total_capital)'),
        ("metric('Total Cash')", 'money(item.withdrawable_cash)'),
        ("metric('Positions')", 'money(item.positions)'),
        ("metric('Book Value')", 'money(item.book_value)'),
    )
    positions = []
    for label, formatter in expected:
        assert label in TEMPLATE
        assert formatter in TEMPLATE
        positions.append(TEMPLATE.index(label))
    assert positions == sorted(positions)


def test_capital_event_ledger_uses_shared_table_and_financial_contracts():
    assert 'table records-table records-table--portfolio-events' in TEMPLATE
    assert '{{ record_type(event.event_type) }}' in TEMPLATE
    assert "money(event.amount_delta, tone='sign', signed=true)" in TEMPLATE
    assert '>Total Amount</th>' in TEMPLATE
    assert 'Capital Events for {{ item.portfolio.name }}' in TEMPLATE
    assert 'table-light' not in TEMPLATE
    assert 'table-hover' not in TEMPLATE
    assert 'class="small records-cell' not in TEMPLATE

    row_hover = _rule(COMPONENTS_CSS, '.table tbody tr:hover > *')
    assert 'background-color: var(--muted-half)' in row_hover

    for role, token in (
        ('positive', '--financial-positive'),
        ('negative', '--financial-negative'),
        ('neutral', '--financial-flat'),
    ):
        rule = _rule(COMPONENTS_CSS, f'.record-type--{role}')
        assert f'color: var({token})' in rule
        assert '--destructive' not in rule
        assert '--chart-' not in rule


def test_action_menus_and_dialogs_use_clear_title_case_contracts():
    for label in (
        'Rename', 'Deposit', 'Withdraw', 'Remove',
        'Edit', 'New Portfolio', 'Rename Portfolio',
        'Edit Capital Entry', 'Remove Capital Entry', 'Save Changes',
    ):
        assert label in TEMPLATE

    assert TEMPLATE.count('dropdown-item--danger') == 2
    assert TEMPLATE.count('class="btn btn-danger"') == 2
    assert TEMPLATE.count('<span>Remove</span>') == 2
    assert TEMPLATE.count("{{ icon('trash') }}Remove") == 2
    assert 'aria-describedby="deletePortfolioDescription"' in TEMPLATE
    assert 'aria-describedby="deletePortfolioEventDescription"' in TEMPLATE
    assert 'bi-' not in TEMPLATE


def test_portfolio_forms_and_withdraw_max_contract_are_unchanged():
    for form_id in (
        'depositFundsForm', 'withdrawFundsForm', 'renamePortfolioForm',
        'deletePortfolioForm', 'editPortfolioEventForm',
        'deletePortfolioEventForm',
    ):
        assert f'id="{form_id}"' in TEMPLATE
    assert TEMPLATE.count('name="csrf_token"') == 7
    assert 'name="amount_delta"' in TEMPLATE
    assert 'name="deposit_date"' in TEMPLATE
    assert 'name="withdraw_date"' in TEMPLATE
    assert 'name="edit_cash_event_amount"' in TEMPLATE
    assert 'name="date"' in TEMPLATE
    assert 'Available To Withdraw' not in TEMPLATE
    assert 'withdraw-available-hint' not in TEMPLATE
    assert 'id="withdraw_max_btn">Max</button>' in TEMPLATE
    assert "amountInput.value = maxAmount;" in TEMPLATE


def test_disclosure_paint_uses_canonical_roles_without_chart_or_raw_colors():
    section = APP_CSS.split('5. DISCLOSURE LIST', 1)[1].split(
        '6. ASSETS TOOLBAR', 1
    )[0]
    assert '--fg-' not in section
    assert '--bg-' not in section
    assert '--chart-' not in section
    assert '--portfolio-chart-' not in section
    assert not re.search(r'#[0-9a-f]{3,8}\b|(?:oklch|rgba?)\(', section, re.I)
    assert 'var(--muted-foreground)' in section
    assert 'var(--foreground)' in section
    assert 'var(--border)' in section
    assert 'var(--card)' in section


def test_responsive_and_accessible_portfolio_structure_remains_present():
    assert '@media (max-width: 75rem)' in APP_CSS
    assert '@media (max-width: 56rem)' in APP_CSS
    assert '.disclosure__toggle {' in APP_CSS
    assert 'min-width: 0' in _rule(APP_CSS, '.disclosure__toggle')
    assert 'text-overflow: ellipsis' in _rule(APP_CSS, '.disclosure__name')
    assert 'role="row"' not in TEMPLATE  # Native table semantics own the ledger.
    assert 'aria-labelledby="depositFundsModalTitle"' in TEMPLATE
    assert 'aria-labelledby="withdrawFundsModalTitle"' in TEMPLATE
    assert 'aria-labelledby="newPortfolioModalTitle"' in TEMPLATE


def test_portfolio_scope_has_no_visualization_or_raw_component_colors():
    assert '--portfolio-chart-' not in TEMPLATE
    assert '--chart-' not in TEMPLATE
    assert not re.search(r'(?:style|color|background)="[^"]*#[0-9a-f]{3,8}', TEMPLATE, re.I)
